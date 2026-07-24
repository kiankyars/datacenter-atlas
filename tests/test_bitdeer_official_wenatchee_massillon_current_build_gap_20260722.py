from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import shutil
import stat

import pytest

try:
    from datacenter_atlas.datacenter_atlas import (
        bitdeer_official_wenatchee_massillon_current_build_gap_20260722 as tranche,
    )
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import (  # type: ignore[no-redef]
        bitdeer_official_wenatchee_massillon_current_build_gap_20260722 as tranche,
    )


def test_exact_two_source_contract_and_strict_import_shape() -> None:
    documents = tranche.expected_source_documents()
    assert tuple(documents) == tranche.SOURCE_FILENAMES
    assert len(documents) == 2
    assert {
        document[entity]["stable_key"]
        for document in documents.values()
        for entity in ("campus", "project")
    } == {
        tranche.WENATCHEE_CAMPUS,
        tranche.WENATCHEE_PROJECT,
        tranche.MASSILLON_CAMPUS,
        tranche.MASSILLON_PROJECT,
    }
    assert [
        (row["value"], row["as_of_date"])
        for document in documents.values()
        for row in document["lifecycle"]
    ] == [
        ("site_preparation", "2026-07-21"),
        ("under_construction", "2026-07-21"),
    ]
    for document in documents.values():
        assert document["schema_version"] == "1.1"
        assert document["operating_models"] == []
        assert document["workloads"] == []
        for entity in ("campus", "project"):
            assert document[entity]["roles"] == {}
            assert document[entity]["coordinates"] is None
            assert document[entity]["geometry"] is None


def test_capacity_boundary_has_only_massillon_26_planned_gross() -> None:
    documents = tranche.expected_source_documents()
    wenatchee = documents[tranche.WENATCHEE_FILENAME]
    massillon = documents[tranche.MASSILLON_FILENAME]
    assert wenatchee["capacities"] == []
    assert [
        (row["entity"], row["metric"], row["stage"], row["base"])
        for row in massillon["capacities"]
    ] == [("project", "gross_facility_mw", "planned", 26.0)]
    metadata = wenatchee["evidence"][0]["metadata"]
    assert metadata["section_label"] == "Online Electrical Capacity"
    assert metadata["online_electrical_capacity_as_reported"] == "13 MW."
    assert "not Pipeline Electrical Capacity" in metadata["capacity_exclusion"]
    massillon_metadata = massillon["evidence"][0]["metadata"]
    assert massillon_metadata["table_capacity_cell_as_reported"] == "21 / 26"
    assert "No 21 MW row" in massillon_metadata["twenty_one_mw_exclusion"]
    assert "No 47 MW" in massillon_metadata["nonadditivity_guardrail"]
    assert "174 MW" in massillon_metadata["campus_total_exclusion"]
    assert "current consumption" in massillon_metadata["consumption_guardrail"]


def test_raw_sec_lineage_is_closed_and_exact() -> None:
    directory = (
        tranche.CAPTURE_ORIGIN
        if tranche.CAPTURE_ORIGIN.exists()
        else tranche.CAPTURE_TRASH
    )
    tranche._validate_capture_directory(directory)
    assert len(tranche.CAPTURES) == 6
    assert len(tranche.CAPTURE_FILE_PINS) == 12
    assert sum(size for size, _digest in tranche.CAPTURE_FILE_PINS.values()) == 237_599
    assert tranche.tree_digest(directory) == tranche.CAPTURE_TREE_SHA256
    assert tranche.SEC_ACCESSION == "0001213900-26-079816"
    assert tranche.SEC_EXHIBIT_FILENAME == "ea029852701ex99-1.htm"
    assert tranche.CAPTURE_FILE_PINS["exhibit99-1.htm"][1] == (
        "c8fe8dcc3d3e264850657dd741d185cc4450188bd0063cd218bf99810f3ea50d"
    )


@pytest.mark.parametrize(
    ("candidate_id", "required_fragment"),
    [
        ("bitdeer-knoxville-ai-conversion", "Design only"),
        ("bitdeer-tydal-conversion", "Planning, design, procurement"),
        ("bitdeer-clarington", "Design/preparation"),
        ("bitdeer-niles", "Grid/site agreement"),
        ("bitdeer-rockdale-pipeline", "Planning only"),
        ("bitdeer-cyberjaya-pipeline", "Ambiguous progress"),
        ("bitdeer-johor-bahru-lease", "Lease and future handover"),
        ("bitdeer-molde-ai-assessment", "Early assessment"),
        ("bitdeer-fox-creek-data-center-design", "power-plant groundbreaking"),
    ],
)
def test_each_review_only_exclusion_is_negative(
    candidate_id: str, required_fragment: str
) -> None:
    assessment = tranche._candidate_assessment("2026-07-22T03:20:00Z")
    candidates = {row["candidate_id"]: row for row in assessment["candidates"]}
    row = candidates[candidate_id]
    assert row["decision"] == "review_only_no_direct_physical_data_center_observation"
    assert required_fragment in row["exclusion"]
    assert row["normalized_entity"] is None
    assert row["normalized_lifecycle"] is None
    assert row["normalized_capacity"] is None
    assert candidate_id not in json.dumps(tranche.expected_source_documents())


def test_v92_collision_and_fox_creek_nonmutation_witnesses() -> None:
    witness = tranche._collision_witness(tranche.expected_source_documents())
    assert witness["v92_selected_input_count"] == 485
    assert witness["v92_entity_count"] == 988
    assert witness["planned_distinct_stable_keys"] == 4
    assert witness["planned_distinct_evidence_keys"] == 2
    assert witness["exact_v92_stable_key_collisions"] == []
    assert witness["exact_v92_evidence_key_collisions"] == []
    assert witness["unexpected_source_collisions"] == {}
    fox = witness["fox_creek_nonmutation"]
    assert fox["sha256"] == tranche.FOX_CREEK_PIN[1]
    assert fox["ctime_ns"] == tranche.FOX_CREEK_PIN[2]
    assert fox["mutated"] is False
    assert fox["new_physical_observation_added"] is False


def test_private_stage_is_hidden_and_replays_offline() -> None:
    if tranche.ARTIFACT.exists():
        assert tranche.validate_artifact()["curated_source_records"] == 2
        return
    final_state = {
        path: path.exists()
        for path in [
            tranche.ARTIFACT,
            *(tranche.SOURCES_ROOT / name for name in tranche.SOURCE_FILENAMES),
        ]
    }
    assert set(final_state.values()) == {False}
    recorded_at = (
        datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=30)
    ).isoformat().replace("+00:00", "Z")
    prepared = tranche._prepare(recorded_at)
    try:
        assert all(path.exists() is state for path, state in final_state.items())
        manifest = tranche.validate_artifact(
            prepared.artifact_stage,
            source_paths=tranche._source_paths(prepared.source_stage),
            require_live=False,
            require_frozen=False,
            wall_clock=tranche._instant(recorded_at),
        )
        assert manifest["curated_source_records"] == 2
        snapshot = json.loads(
            (prepared.artifact_stage / "source-snapshot.json").read_text()
        )
        assert snapshot["totals"]["distinct_entities"] == 4
        assert snapshot["totals"]["lifecycle_observations"] == 2
        assert snapshot["totals"]["capacity_estimates"] == 1
        assert snapshot["totals"]["planned_gross_facility_mw_sum"] == 26.0
    finally:
        if prepared.source_stage.exists():
            shutil.rmtree(prepared.source_stage)
        if prepared.artifact_stage.exists():
            shutil.rmtree(prepared.artifact_stage)


def test_chmod_freeze_changes_only_staged_publication_members(tmp_path) -> None:
    source_stage = tmp_path / "sources"
    artifact_stage = tmp_path / "artifact"
    source_stage.mkdir()
    artifact_stage.mkdir()
    documents = tranche.expected_source_documents()
    tranche._write_source_stage(source_stage, documents)
    tranche._write_artifact_stage(
        artifact_stage, "2000-01-01T00:00:00Z", documents
    )
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o600
        for path in source_stage.iterdir()
    )
    assert stat.S_IMODE(artifact_stage.stat().st_mode) == 0o700
    prepared = tranche._Prepared(
        source_stage, artifact_stage, "2000-01-01T00:00:00Z"
    )
    tranche._freeze_after_barrier(prepared)
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o444
        for path in source_stage.iterdir()
    )
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o444
        for path in artifact_stage.iterdir()
    )
    assert stat.S_IMODE(artifact_stage.stat().st_mode) == 0o555
    assert tranche._require_fox_creek_nonmutation()["ctime_ns"] == tranche.FOX_CREEK_PIN[2]


def test_partial_final_collision_fails_closed(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(tranche, "SOURCES_ROOT", tmp_path)
    monkeypatch.setattr(tranche, "ARTIFACT", tmp_path / "artifact")
    (tmp_path / tranche.SOURCE_FILENAMES[0]).write_text("collision")
    with pytest.raises(RuntimeError, match="partial Bitdeer final-path collision"):
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
        if calls == 2:
            raise FileExistsError("injected Bitdeer collision")
        original(source, destination)

    monkeypatch.setattr(tranche, "_promote_noreplace", collide)
    try:
        with pytest.raises(FileExistsError, match="injected Bitdeer collision"):
            tranche._publish(prepared)
        assert not any(source_root.glob("curated-*.json"))
        assert not tranche.ARTIFACT.exists()
    finally:
        if source_stage.exists():
            shutil.rmtree(source_stage)
        if artifact_stage.exists():
            shutil.rmtree(artifact_stage)


def test_live_chronology_tamper_and_residue_after_publication(tmp_path) -> None:
    if not tranche.ARTIFACT.exists():
        pytest.skip("Bitdeer artifact not published yet")
    manifest = tranche.validate_artifact()
    before = tranche._instant(manifest["recorded_at"]) - timedelta(microseconds=1)
    with pytest.raises(RuntimeError, match="recorded_at is not live"):
        tranche.validate_artifact(wall_clock=before)
    assert not tranche.PUBLICATION_LOCK.exists()
    assert not list(tranche.SOURCES_ROOT.glob(".bitdeer-sec-current-build-sources.*"))
    assert not list(tranche.ARTIFACT_ROOT.glob(f".{tranche.ARTIFACT_ID}.*"))
    copied = tmp_path / "artifact-copy"
    shutil.copytree(tranche.ARTIFACT, copied)
    copied.chmod(0o755)
    target = copied / "source-snapshot.json"
    target.chmod(0o644)
    target.write_bytes(target.read_bytes() + b" ")
    target.chmod(0o444)
    copied.chmod(0o555)
    with pytest.raises(RuntimeError, match="manifest pin differs"):
        tranche.validate_artifact(copied)
