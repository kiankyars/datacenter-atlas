from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import shutil

import pytest

try:
    from datacenter_atlas.datacenter_atlas import (
        aws_official_clinton_adaptive_reuse_current_build_gap_20260722 as tranche,
    )
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import (  # type: ignore[no-redef]
        aws_official_clinton_adaptive_reuse_current_build_gap_20260722 as tranche,
    )


def test_exact_source_contract_has_one_dated_construction_observation() -> None:
    documents = tranche.expected_source_documents()
    assert tuple(documents) == tranche.SOURCE_FILENAMES
    document = documents[tranche.SOURCE_FILENAME]
    assert document["campus"]["stable_key"] == tranche.CAMPUS_KEY
    assert document["project"]["stable_key"] == tranche.PROJECT_KEY
    assert len(document["evidence"]) == 4
    assert document["lifecycle"] == [
        {
            "entity": "project",
            "value": "under_construction",
            "evidence_key": tranche.PRIMARY_EVIDENCE_KEY,
            "as_of_date": "2026-03-03",
            "method": "authoritative_physical_status_update",
            "confidence": 0.95,
        }
    ]
    assert document["capacities"] == []
    assert document["operating_models"] == []
    assert document["workloads"] == []
    for entity in ("campus", "project"):
        assert document[entity]["roles"] == {}
        assert document[entity]["coordinates"] is None
        assert document[entity]["geometry"] is None


def test_identity_join_metadata_and_zero_normalization_boundaries() -> None:
    assessment = tranche._candidate_assessment("2026-07-22T02:00:00Z")
    candidate = assessment["candidates"][0]
    assert candidate["identity_join"] == {
        "physical_observation_evidence_key": tranche.PRIMARY_EVIDENCE_KEY,
        "identity_resolution_evidence_key": tranche.IDENTITY_EVIDENCE_KEY,
        "physical_observation_date": "2026-03-03",
        "identity_resolution_date": "2026-06-09",
        "operator_withheld_at_physical_observation": True,
        "resolved_operator_context": "AWS",
        "resolved_asset_context": "former Delphi manufacturing facility",
    }
    assert candidate["lifecycle"]["current_status_persisted"] is False
    assert candidate["normalized_capacity"] is None
    assert [row["value"] for row in candidate["reported_context_not_normalized"]] == [
        1_000_000_000,
        25_000_000_000,
        100,
        2_000,
    ]
    liveblog = next(
        row
        for row in tranche.expected_source_documents()[tranche.SOURCE_FILENAME][
            "evidence"
        ]
        if row["key"] == "amazon-clinton-former-delphi-liveblog-item-2026-06-09"
    )
    assert liveblog["published_at"] == "2026-06-09"
    assert liveblog["metadata"]["item_timestamp"] == "2026-06-09T16:33:15Z"
    assert "unrelated items" in liveblog["metadata"]["page_date_guardrail"]


def test_v91_collision_witness_is_exact_and_immutable() -> None:
    witness = tranche._collision_witness(tranche.expected_source_documents())
    assert witness["v91_selected_input_count"] == 480
    assert witness["v91_entity_count"] == 978
    assert witness["exact_v91_stable_key_collisions"] == []
    assert witness["exact_v91_evidence_key_collisions"] == []
    assert witness["exact_v91_address_matches"] == []
    assert witness["v91_clinton_delphi_keyword_matches"] == []
    assert witness["exact_existing_identity_keys_reused"] == []


def test_capture_set_is_closed_and_exact() -> None:
    directory = (
        tranche.resolve_external_capture(tranche.CAPTURE_ORIGIN, tranche.CAPTURE_TRASH)
    )
    tranche._validate_capture_directory(directory)
    assert len(tranche.CAPTURES) == 4
    assert len(tranche.CAPTURE_FILE_PINS) == 8
    assert sum(size for size, _digest in tranche.CAPTURE_FILE_PINS.values()) == 1_960_857


def test_private_stage_replays_offline_and_has_no_final_path_side_effect() -> None:
    if tranche.ARTIFACT.exists():
        manifest = tranche.validate_artifact()
        assert manifest["curated_source_records"] == 1
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
        assert manifest["curated_source_records"] == 1
        snapshot = json.loads(
            (prepared.artifact_stage / "source-snapshot.json").read_text()
        )
        for key in (
            "capacity_estimates",
            "normalized_critical_it_mw_sum",
            "annual_energy_estimates",
            "pue_estimates",
            "wue_estimates",
            "operating_model_observations",
            "workload_observations",
            "coordinates_present",
            "geometry_present",
            "satellite_observations",
            "computer_vision_observations",
            "unique_physical_sites_claimed",
        ):
            assert snapshot["totals"][key] == 0
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
    with pytest.raises(
        RuntimeError, match="partial AWS Clinton source final-path collision"
    ):
        tranche.build(recorded_at="2099-01-01T00:00:00Z")


def test_late_collision_rolls_back_promoted_source(tmp_path, monkeypatch) -> None:
    source_root = tmp_path / "sources"
    artifact_root = tmp_path / "artifacts"
    source_root.mkdir()
    artifact_root.mkdir()
    documents = tranche.expected_source_documents()
    source_stage = Path(tranche.tempfile.mkdtemp(dir=source_root))
    artifact_stage = Path(tranche.tempfile.mkdtemp(dir=artifact_root))
    tranche._write_source_stage(source_stage, documents)
    tranche._write_artifact_stage(
        artifact_stage, "2099-01-01T00:00:00Z", documents
    )
    monkeypatch.setattr(tranche, "SOURCES_ROOT", source_root)
    monkeypatch.setattr(tranche, "ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr(
        tranche, "ARTIFACT", artifact_root / tranche.ARTIFACT_ID
    )
    prepared = tranche._Prepared(
        source_stage, artifact_stage, "2099-01-01T00:00:00Z"
    )
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
    monkeypatch.setattr(
        tranche,
        "_instant",
        lambda _value: datetime.now(UTC) - timedelta(seconds=1),
    )
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
