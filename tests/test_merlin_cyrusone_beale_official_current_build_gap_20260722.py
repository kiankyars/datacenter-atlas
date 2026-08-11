from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import shutil

import pytest

try:
    from datacenter_atlas.datacenter_atlas import (
        merlin_cyrusone_beale_official_current_build_gap_20260722 as tranche,
    )
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import (  # type: ignore[no-redef]
        merlin_cyrusone_beale_official_current_build_gap_20260722 as tranche,
    )


def test_exact_source_entity_lifecycle_and_capacity_contract() -> None:
    documents = tranche.expected_source_documents()
    assert tuple(documents) == tranche.SOURCE_FILENAMES
    assert len(documents) == 6
    assert len(
        {
            document[entity]["stable_key"]
            for document in documents.values()
            for entity in ("campus", "project")
        }
    ) == 11
    assert len({document["campus"]["stable_key"] for document in documents.values()}) == 5
    assert len({document["project"]["stable_key"] for document in documents.values()}) == 6
    assert sum(len(document["lifecycle"]) for document in documents.values()) == 8
    capacities = [row for document in documents.values() for row in document["capacities"]]
    assert sorted((row["entity"], row["metric"], row["stage"], row["base"]) for row in capacities) == [
        ("campus", "critical_it_mw", "planned", 54.0),
        ("project", "critical_it_mw", "planned", 18.0),
    ]
    for document in documents.values():
        assert document["operating_models"] == []
        assert document["workloads"] == []
        for entity in ("campus", "project"):
            assert document[entity]["roles"] == {}
            assert document[entity]["coordinates"] is None
            assert document[entity]["geometry"] is None


def test_merlin_uses_two_v11_records_and_one_idempotent_campus() -> None:
    documents = tranche.expected_source_documents()
    merlin = [documents[name] for name in tranche.SOURCE_FILENAMES[:2]]
    assert {document["schema_version"] for document in merlin} == {"1.1"}
    assert {document["campus"]["stable_key"] for document in merlin} == {
        tranche.MERLIN_CAMPUS
    }
    assert {document["project"]["stable_key"].rsplit(":", 1)[-1] for document in merlin} == {
        "building-2-current-build",
        "building-3-current-build",
    }
    assert all(document["capacities"] == [] for document in merlin)
    serialized = json.dumps(merlin, sort_keys=True)
    assert "+162 MW" in serialized
    assert "PUE 1.15" in serialized
    assert "WUE 0" in serialized


def test_wood_tulsa_and_pima_preserve_temporal_rows_without_extrapolation() -> None:
    documents = tranche.expected_source_documents()
    wood = documents[tranche.SOURCE_FILENAMES[3]]
    tulsa = documents[tranche.SOURCE_FILENAMES[4]]
    pima = documents[tranche.SOURCE_FILENAMES[5]]
    assert [(row["value"], row["as_of_date"]) for row in wood["lifecycle"]] == [
        ("shell", "2025-05-13"),
        ("under_construction", "2025-08-12"),
    ]
    assert [(row["value"], row["as_of_date"]) for row in tulsa["lifecycle"]] == [
        ("under_construction", "2025-10-31"),
        ("under_construction", "2025-11-24"),
    ]
    assert [(row["value"], row["as_of_date"]) for row in pima["lifecycle"]] == [
        ("site_preparation", "2026-05-11")
    ]
    response = next(
        row
        for row in pima["evidence"]
        if row["key"] == "pima-project-blue-pause-response-2026-05-22"
    )
    assert "Major earthwork halted" in response["metadata"]["pause_context"]
    assert "Current status is unknown" in response["metadata"]["normalization_decision"]


def test_capture_and_collision_witnesses_are_closed_and_pinned() -> None:
    directory = (
        tranche.resolve_external_capture(tranche.CAPTURE_ORIGIN, tranche.CAPTURE_TRASH)
    )
    tranche._validate_capture_directory(directory)
    assert len(tranche.CAPTURES) == 15
    assert len(tranche.CAPTURE_FILE_PINS) == 30
    assert sum(size for size, _digest in tranche.CAPTURE_FILE_PINS.values()) == 13_100_740
    witness = tranche._collision_witness(tranche.expected_source_documents())
    assert witness["v92_selected_input_count"] == 485
    assert witness["v92_entity_count"] == 988
    assert witness["planned_distinct_stable_keys"] == 11
    assert witness["planned_distinct_evidence_keys"] == 11
    assert witness["exact_v92_stable_key_collisions"] == []
    assert witness["exact_v92_evidence_key_collisions"] == []


def test_private_stage_replays_offline_without_final_path_side_effect() -> None:
    if tranche.ARTIFACT.exists():
        manifest = tranche.validate_artifact()
        assert manifest["curated_source_records"] == 6
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
            require_frozen=False,
            wall_clock=tranche._instant(recorded_at),
        )
        assert manifest["curated_source_records"] == 6
        snapshot = json.loads(
            (prepared.artifact_stage / "source-snapshot.json").read_text()
        )
        assert snapshot["totals"]["distinct_entities_in_source_records"] == 11
        assert snapshot["totals"]["unique_imported_entity_snapshots"] == 11
        assert snapshot["totals"]["lifecycle_observations"] == 8
        assert snapshot["totals"]["capacity_estimates"] == 2
        assert snapshot["totals"]["coordinates_present"] == 0
        assert snapshot["totals"]["geometry_present"] == 0
    finally:
        if prepared.source_stage.exists():
            shutil.rmtree(prepared.source_stage)
        if prepared.artifact_stage.exists():
            shutil.rmtree(prepared.artifact_stage)


def test_partial_final_collision_fails_closed(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(tranche, "SOURCES_ROOT", tmp_path)
    monkeypatch.setattr(tranche, "ARTIFACT", tmp_path / "artifact")
    (tmp_path / tranche.SOURCE_FILENAMES[0]).write_text("collision")
    with pytest.raises(RuntimeError, match="partial official-source final-path collision"):
        tranche.build(recorded_at="2099-01-01T00:00:00Z")


def test_late_collision_rolls_back_every_promoted_source(tmp_path, monkeypatch) -> None:
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
    monkeypatch.setattr(tranche, "ARTIFACT", artifact_root / tranche.ARTIFACT_ID)
    monkeypatch.setattr(tranche, "_freeze_after_barrier", lambda _prepared: None)
    prepared = tranche._Prepared(
        source_stage, artifact_stage, "2099-01-01T00:00:00Z"
    )
    original = tranche._promote_noreplace
    calls = 0

    def collide(source: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 4:
            raise FileExistsError("injected late collision")
        original(source, destination)

    monkeypatch.setattr(tranche, "_promote_noreplace", collide)
    try:
        with pytest.raises(FileExistsError, match="injected late collision"):
            tranche._publish(prepared)
        assert not any(source_root.glob("curated-*.json"))
        assert not tranche.ARTIFACT.exists()
    finally:
        if source_stage.exists():
            shutil.rmtree(source_stage)
        if artifact_stage.exists():
            shutil.rmtree(artifact_stage)


def test_future_time_tamper_and_chronology_guards_after_publication(
    tmp_path,
) -> None:
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


def test_no_private_staging_or_lock_residue_after_publication() -> None:
    if not tranche.ARTIFACT.exists():
        pytest.skip("final artifact not published yet")
    assert not tranche.PUBLICATION_LOCK.exists()
    assert not list(tranche.SOURCES_ROOT.glob(".merlin-cyrusone-beale-sources.*"))
    assert not list(tranche.ARTIFACT_ROOT.glob(f".{tranche.ARTIFACT_ID}.*"))
