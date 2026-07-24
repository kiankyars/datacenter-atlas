from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import shutil
import stat

import pytest

try:
    from datacenter_atlas.datacenter_atlas import (
        official_nordic_iren_current_build_gap_20260722 as tranche,
    )
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import (  # type: ignore[no-redef]
        official_nordic_iren_current_build_gap_20260722 as tranche,
    )


def _all_capacities() -> list[dict[str, object]]:
    return [
        row
        for document in tranche.expected_source_documents().values()
        for row in document["capacities"]
    ]


def test_exact_four_source_and_eight_entity_contract() -> None:
    documents = tranche.expected_source_documents()
    assert tuple(documents) == tranche.SOURCE_FILENAMES
    assert len(documents) == 4
    assert {
        document[entity]["stable_key"]
        for document in documents.values()
        for entity in ("campus", "project")
    } == {
        tranche.NSCALE_CAMPUS,
        tranche.NSCALE_PROJECT,
        tranche.NORTHC_CAMPUS,
        tranche.NORTHC_PROJECT,
        tranche.IREN_CAMPUS,
        tranche.IREN_PROJECT,
        tranche.BITZERO_CAMPUS,
        tranche.BITZERO_PROJECT,
    }
    assert sum(len(document["evidence"]) for document in documents.values()) == 9
    for document in documents.values():
        assert document["schema_version"] == "1.1"
        assert document["operating_models"] == []
        assert document["workloads"] == []
        for entity in ("campus", "project"):
            assert document[entity]["coordinates"] is None
            assert document[entity]["geometry"] is None


def test_exact_lifecycle_contract_and_scope() -> None:
    documents = tranche.expected_source_documents()
    assert [
        (document["project"]["stable_key"], row["value"], row["as_of_date"])
        for document in documents.values()
        for row in document["lifecycle"]
    ] == [
        (tranche.NSCALE_PROJECT, "under_construction", "2026-07-06"),
        (tranche.NORTHC_PROJECT, "expansion", "2026-04-01"),
        (tranche.IREN_PROJECT, "under_construction", "2026-05-07"),
        (tranche.BITZERO_PROJECT, "foundations", "2026-06-15"),
    ]
    bitzero = documents[tranche.BITZERO_FILENAME]
    metadata = bitzero["evidence"][0]["metadata"]
    assert (
        "scoped only to two transformer foundations"
        in metadata["physical_status_scope"]
    )
    assert "not a data-hall" in metadata["physical_status_scope"]


def test_capacity_boundary_is_exactly_northc_and_iren_critical_it() -> None:
    assert [
        (row["metric"], row["stage"], row["base"], row["evidence_key"])
        for row in _all_capacities()
    ] == [
        (
            "critical_it_mw",
            "planned",
            2.4,
            tranche.NORTHC_EXPANSION_EVIDENCE,
        ),
        (
            "critical_it_mw",
            "contracted",
            200.0,
            tranche.IREN_CONTRACT_EVIDENCE,
        ),
    ]
    serialized = json.dumps(tranche.expected_source_documents(), sort_keys=True)
    for fragment in ("25 MW", "14 MW", "750 MW", "two new 60 MW", "70 MW", "110 MW"):
        assert fragment in serialized
    for row in _all_capacities():
        assert row["base"] not in {14, 25, 60, 70, 110, 750}


def test_northc_exact_address_and_phase_nonadditivity() -> None:
    document = tranche.expected_source_documents()[tranche.NORTHC_FILENAME]
    assert document["campus"]["address"] == (
        "Lakenblekerstraat 13, 1431 GE Aalsmeer, Netherlands"
    )
    assert document["project"]["address"] == document["campus"]["address"]
    article = document["evidence"][0]["metadata"]
    facility = document["evidence"][1]["metadata"]
    assert article["floor_area_metadata"] == "1,800 m2 extra data floor for phase 2"
    assert "not added to phase 2" in article["phase_1_nonadditivity_guardrail"]
    assert facility["whole_facility_electrical_power_as_reported"] == "14 MW"
    assert "not phase-2" in facility["capacity_exclusion"]


def test_iren_grouped_contract_boundary() -> None:
    document = tranche.expected_source_documents()[tranche.IREN_FILENAME]
    assert document["project"]["roles"]["customer"] == ["Microsoft"]
    contract = document["evidence"][0]["metadata"]
    assert contract["contract_effective_date"] == "2025-11-02"
    assert "No per-Horizon entity" in contract["grouped_boundary_guardrail"]
    assert "not treated as a real-estate lease" in contract["customer_scope"]
    assert document["operating_models"] == []
    assert document["workloads"] == []


def test_bitzero_70mw_is_metadata_only() -> None:
    document = tranche.expected_source_documents()[tranche.BITZERO_FILENAME]
    assert document["capacities"] == []
    april = document["evidence"][1]["metadata"]
    assert april["energization_language_as_reported"] == (
        "confirmed 70MW expected to be energized in Q4 2026"
    )
    assert "not unambiguously type 70 MW" in april["capacity_exclusion"]
    assert "forward-looking" in april["capacity_exclusion"]


def test_raw_capture_closed_inventory_and_exact_tree() -> None:
    directory = (
        tranche.CAPTURE_ORIGIN
        if tranche.CAPTURE_ORIGIN.exists()
        else tranche.CAPTURE_TRASH
    )
    tranche._validate_capture_directory(directory)
    assert len(tranche.CAPTURES) == 17
    assert len(tranche.CAPTURE_FILE_PINS) == 34
    assert sum(size for size, _digest in tranche.CAPTURE_FILE_PINS.values()) == (
        tranche.CAPTURE_TOTAL_BYTES
    )
    assert tranche.tree_digest(directory) == tranche.CAPTURE_TREE_SHA256
    assert tranche.CAPTURE_FILE_PINS["iren_10q_submission.txt"][0] == 23_700_666


def test_v93_and_known_v94_noncollision_witness() -> None:
    witness = tranche._collision_witness(tranche.expected_source_documents())
    assert witness["v93_selected_input_count"] == 488
    assert witness["v93_entity_count"] == 994
    assert witness["planned_distinct_stable_keys"] == 8
    assert witness["planned_distinct_evidence_keys"] == 9
    assert witness["exact_v93_stable_key_collisions"] == []
    assert witness["exact_v93_evidence_key_collisions"] == []
    assert witness["unexpected_source_collisions"] == {}
    known = witness["known_v94_noncollision"]
    assert known["known_source_count"] == 10
    assert known["unfinished_open_seed_v94_bytes_required"] is False
    assert all(row["bytes_or_hash_dependency"] is False for row in known["sources"])


def test_candidate_assessment_closes_every_excluded_number() -> None:
    assessment = tranche._candidate_assessment("2026-07-22T04:30:00Z")
    assert assessment["candidate_count"] == 12
    assert assessment["seed_eligible_candidate_count"] == 4
    assert assessment["review_only_count"] == 8
    review = {
        row["candidate_id"]: row
        for row in assessment["candidates"]
        if row["decision"].startswith("review_only")
    }
    assert set(review) == {row["candidate_id"] for row in tranche.REVIEW_ONLY}
    for row in review.values():
        assert row["normalized_entity"] is None
        assert row["normalized_lifecycle"] is None
        assert row["normalized_capacity"] is None


def test_private_stage_is_hidden_and_replays_deterministically() -> None:
    if tranche.ARTIFACT.exists():
        assert tranche.validate_artifact()["curated_source_records"] == 4
        return
    final_paths = [
        tranche.ARTIFACT,
        *(tranche.SOURCES_ROOT / name for name in tranche.SOURCE_FILENAMES),
    ]
    assert not any(path.exists() or path.is_symlink() for path in final_paths)
    recorded_at = (
        (datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=30))
        .isoformat()
        .replace("+00:00", "Z")
    )
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
        assert manifest["curated_source_records"] == 4
        assert manifest["successful_http_200_body_captures"] == 17
        snapshot = json.loads(
            (prepared.artifact_stage / "source-snapshot.json").read_text()
        )
        assert snapshot["totals"]["distinct_entities"] == 8
        assert snapshot["totals"]["unique_evidence_records"] == 9
        assert snapshot["totals"]["capacity_estimates"] == 2
    finally:
        if prepared.source_stage.exists():
            shutil.rmtree(prepared.source_stage)
        if prepared.artifact_stage.exists():
            shutil.rmtree(prepared.artifact_stage)


def test_freeze_changes_only_staged_members(tmp_path: Path) -> None:
    source_stage = tmp_path / "sources"
    artifact_stage = tmp_path / "artifact"
    source_stage.mkdir()
    artifact_stage.mkdir()
    documents = tranche.expected_source_documents()
    tranche._write_source_stage(source_stage, documents)
    tranche._write_artifact_stage(artifact_stage, "2000-01-01T00:00:00Z", documents)
    prepared = tranche._Prepared(source_stage, artifact_stage, "2000-01-01T00:00:00Z")
    tranche._freeze_after_barrier(prepared)
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o444 for path in source_stage.iterdir()
    )
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o444 for path in artifact_stage.iterdir()
    )
    assert stat.S_IMODE(artifact_stage.stat().st_mode) == 0o555


def test_source_and_artifact_tamper_fail_closed(tmp_path: Path) -> None:
    source_stage = tmp_path / "sources"
    artifact_stage = tmp_path / "artifact"
    source_stage.mkdir()
    artifact_stage.mkdir()
    documents = tranche.expected_source_documents()
    tranche._write_source_stage(source_stage, documents)
    tranche._write_artifact_stage(artifact_stage, "2099-01-01T00:00:00Z", documents)
    source = source_stage / tranche.SOURCE_FILENAMES[0]
    source.write_bytes(source.read_bytes() + b"\n")
    with pytest.raises(RuntimeError, match="source differs"):
        tranche.validate_artifact(
            artifact_stage,
            source_paths=tranche._source_paths(source_stage),
            require_live=False,
            require_frozen=False,
            wall_clock=tranche._instant("2099-01-01T00:00:00Z"),
        )
    tranche._write_source_stage(source_stage, documents)
    assessment = artifact_stage / "candidate-assessment.json"
    assessment.write_bytes(assessment.read_bytes() + b"\n")
    with pytest.raises(RuntimeError, match="manifest pin differs"):
        tranche.validate_artifact(
            artifact_stage,
            source_paths=tranche._source_paths(source_stage),
            require_live=False,
            require_frozen=False,
            wall_clock=tranche._instant("2099-01-01T00:00:00Z"),
        )


def test_partial_final_collision_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tranche, "SOURCES_ROOT", tmp_path)
    monkeypatch.setattr(tranche, "ARTIFACT", tmp_path / "artifact")
    (tmp_path / tranche.SOURCE_FILENAMES[0]).write_text("collision")
    with pytest.raises(RuntimeError, match="partial official tranche"):
        tranche.build(recorded_at="2099-01-01T00:00:00Z")


def test_late_collision_rolls_back_only_matching_identities(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    monkeypatch.setattr(tranche, "_freeze_after_barrier", lambda _prepared: None)
    prepared = tranche._Prepared(source_stage, artifact_stage, "2099-01-01T00:00:00Z")
    original = tranche._promote_noreplace
    calls = 0

    def collide(source: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise FileExistsError("injected official collision")
        original(source, destination)

    monkeypatch.setattr(tranche, "_promote_noreplace", collide)
    try:
        with pytest.raises(FileExistsError, match="injected official collision"):
            tranche._publish(prepared)
        assert not any(source_root.glob("curated-*.json"))
        assert not tranche.ARTIFACT.exists()
    finally:
        if source_stage.exists():
            shutil.rmtree(source_stage)
        if artifact_stage.exists():
            shutil.rmtree(artifact_stage)


def test_future_recorded_at_rejected_for_live_artifact() -> None:
    if tranche.ARTIFACT.exists():
        pytest.skip("live artifact already published")
    future = (
        (datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=30))
        .isoformat()
        .replace("+00:00", "Z")
    )
    prepared = tranche._prepare(future)
    try:
        with pytest.raises(RuntimeError, match="recorded_at is not live"):
            tranche.validate_artifact(
                prepared.artifact_stage,
                source_paths=tranche._source_paths(prepared.source_stage),
                require_live=True,
                require_frozen=False,
                wall_clock=datetime.now(UTC),
            )
    finally:
        shutil.rmtree(prepared.source_stage)
        shutil.rmtree(prepared.artifact_stage)


def test_live_chronology_modes_and_no_stage_residue() -> None:
    if not tranche.ARTIFACT.exists():
        pytest.skip("official artifact not published yet")
    manifest = tranche.validate_artifact()
    recorded = tranche._instant(manifest["recorded_at"]).timestamp()
    paths = [
        tranche.ARTIFACT,
        *tranche.ARTIFACT.iterdir(),
        *(tranche.SOURCES_ROOT / name for name in tranche.SOURCE_FILENAMES),
    ]
    assert all(path.stat(follow_symlinks=False).st_ctime >= recorded for path in paths)
    assert stat.S_IMODE(tranche.ARTIFACT.stat().st_mode) == 0o555
    assert not list(tranche.SOURCES_ROOT.glob(".official-nordic-iren-sources.*"))
    assert not list(tranche.ARTIFACT_ROOT.glob(f".{tranche.ARTIFACT_ID}.*"))
    assert not tranche.PUBLICATION_LOCK.exists()
