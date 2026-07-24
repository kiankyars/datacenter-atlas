from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import shutil
import stat

import pytest

try:
    from datacenter_atlas.datacenter_atlas import (
        global_official_batam_jakarta_hanoi_bue1_current_build_gap_20260722 as tranche,
    )
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import (  # type: ignore[no-redef]
        global_official_batam_jakarta_hanoi_bue1_current_build_gap_20260722 as tranche,
    )


def _write_sources(directory: Path, *, mode: int = 0o600) -> dict[str, Path]:
    paths = {}
    for name, document in tranche.expected_source_documents().items():
        path = directory / name
        path.write_bytes(tranche._canonical(document))
        path.chmod(mode)
        paths[name] = path
    return paths


def test_exact_source_shape_and_stable_boundaries() -> None:
    documents = tranche.expected_source_documents()
    assert list(documents) == list(tranche.SOURCE_FILENAMES)
    assert [
        (document["campus"]["stable_key"], document["project"]["stable_key"])
        for document in documents.values()
    ] == [
        (tranche.BTM_CAMPUS, tranche.BTM_PROJECT),
        (tranche.CIRION_CAMPUS, tranche.CIRION_PROJECT),
        (tranche.JAKARTA_CAMPUS, tranche.JAKARTA_PROJECT),
        (tranche.CMC_CAMPUS, tranche.CMC_PROJECT),
    ]
    assert sum(len(document["evidence"]) for document in documents.values()) == 9
    assert all(document["schema_version"] == "1.1" for document in documents.values())
    assert all(
        document[entity][field] is None
        for document in documents.values()
        for entity in ("campus", "project")
        for field in ("coordinates", "geometry")
    )


def test_strict_offline_replay_is_idempotent(tmp_path: Path) -> None:
    paths = _write_sources(tmp_path)
    expected = {
        "entities": 8,
        "entity_snapshots": 8,
        "evidence": 9,
        "lifecycle_observations": 4,
        "operating_model_observations": 1,
        "workload_observations": 0,
        "capacity_estimates": 1,
    }
    first = tranche._offline_import(paths, "2026-07-22T04:30:00Z")
    second = tranche._offline_import(paths, "2026-07-22T04:30:00Z")
    assert first == expected == second


def test_lifecycle_is_exactly_dated_and_never_current_inferred() -> None:
    documents = list(tranche.expected_source_documents().values())
    assert [
        (
            document["project"]["stable_key"],
            row["value"],
            row["as_of_date"],
        )
        for document in documents
        for row in document["lifecycle"]
    ] == [
        (tranche.BTM_PROJECT, "shell", "2025-10-30"),
        (tranche.CIRION_PROJECT, "expansion", "2025-08-21"),
        (tranche.JAKARTA_PROJECT, "under_construction", "2025-06-17"),
        (tranche.CMC_PROJECT, "under_construction", "2025-06-01"),
    ]
    assessment = tranche._candidate_assessment("2026-07-22T04:30:00Z")
    assert assessment["current_status_inferred"] is False
    assert assessment["candidates"][2]["lifecycle"]["current_status"] == "unknown"
    assert assessment["candidates"][3]["lifecycle"]["current_status"] == "unknown"


def test_only_supported_capacity_and_classification_are_normalized() -> None:
    documents = list(tranche.expected_source_documents().values())
    capacities = [row for document in documents for row in document["capacities"]]
    assert [
        (row["entity"], row["metric"], row["stage"], row["base"]) for row in capacities
    ] == [("project", "critical_it_mw", "planned", 18)]
    assert [
        (row["entity"], row["value"], row["as_of_date"])
        for document in documents
        for row in document["operating_models"]
    ] == [("campus", "colocation", "2026-07-22")]
    assert not [row for document in documents for row in document["workloads"]]
    assert {row["metric"] for row in capacities}.isdisjoint(
        {
            "gross_facility_mw",
            "grid_connection_mw",
            "generation_nameplate_mw",
            "annual_energy_mwh",
            "pue",
            "wue_l_per_kwh",
        }
    )


def test_cirion_address_and_peering_capacity_exclusions_are_explicit() -> None:
    document = tranche.expected_source_documents()[tranche.SOURCE_FILENAMES[1]]
    assert document["campus"]["address"] == (
        "Av. del Campo 1301, C1427 Cdad. Autónoma de Buenos Aires, Argentina"
    )
    assert document["project"]["address"] == "Buenos Aires, Argentina"
    assert document["capacities"] == []
    metadata = json.dumps(document["evidence"], sort_keys=True)
    assert "PeeringDB-derived" in metadata
    assert "7 MW installed" in metadata
    assert "greater-than-20 MW" in metadata


def test_damac_is_an_archived_company_disclosure_with_live_500_retained() -> None:
    document = tranche.expected_source_documents()[tranche.SOURCE_FILENAMES[2]]
    evidence = document["evidence"][0]
    spec = tranche.CAPTURE_SPECS["damac_jakarta_wayback"]
    assert evidence["kind"] == "company_disclosure"
    assert evidence["source_url"] == spec.effective_url
    assert evidence["metadata"]["evidence_class"] == "archived_company_disclosure"
    assert evidence["metadata"]["archive_capture_timestamp"] == "20260122183232"
    assert evidence["metadata"]["official_canonical_url"] == (
        spec.original_official_url
    )
    assert document["capacities"] == []
    assert document["operating_models"] == []
    assert document["workloads"] == []
    inventory = tranche._capture_inventory("2026-07-22T04:30:00Z")
    live = next(
        row
        for row in inventory["controlled_captures"]
        if row["capture_id"] == "damac_jakarta"
    )
    assert live["http_status"] == 500
    assert live["contributes_evidence"] is False
    assert live["body"]["sha256"] == tranche.CAPTURE_FILE_PINS["damac_jakarta.body"][1]


def test_cmc_annual_report_is_the_lifecycle_corroboration() -> None:
    document = tranche.expected_source_documents()[tranche.SOURCE_FILENAMES[3]]
    lifecycle = document["lifecycle"][0]
    assert lifecycle["evidence_key"] == tranche.CMC_REPORT_EVIDENCE
    report = next(
        row for row in document["evidence"] if row["key"] == tranche.CMC_REPORT_EVIDENCE
    )
    assert report["metadata"]["selected_pdf_page"] == 50
    assert "distinct five-storey data-center tower" in report["excerpt"]
    assert document["capacities"] == []


def test_raw_capture_is_closed_exact_and_includes_every_failure() -> None:
    directory = (
        tranche.CAPTURE_ORIGIN
        if tranche.CAPTURE_ORIGIN.exists()
        else tranche.CAPTURE_TRASH
    )
    tranche._validate_capture_directory(directory)
    assert len(tranche.CAPTURE_FILE_PINS) == tranche.CAPTURE_FILE_COUNT == 50
    assert sum(size for size, _digest in tranche.CAPTURE_FILE_PINS.values()) == (
        tranche.CAPTURE_TOTAL_BYTES
    )
    assert tranche.tree_digest(directory) == tranche.CAPTURE_TREE_SHA256
    inventory = tranche._capture_inventory("2026-07-22T04:30:00Z")
    assert inventory["direct_request_attempts"] == 13
    assert inventory["archive_replay_attempts"] == 4
    assert inventory["successful_http_200_body_captures"] == 9
    assert inventory["failed_origin_body_captures"] == 8
    assert len(inventory["complete_private_file_inventory"]) == 50


def test_v93_and_known_ten_source_v94_noncollision_is_exact() -> None:
    witness = tranche._collision_witness(tranche.expected_source_documents())
    assert witness["v93_selected_input_count"] == 488
    assert witness["v93_entity_count"] == 994
    assert witness["planned_stable_key_collisions_with_v93"] == []
    assert witness["inflight_v94_source_count_checked"] == 10
    assert witness["planned_stable_key_collisions_with_inflight_v94"] == []
    assert witness["planned_evidence_key_collisions_with_inflight_v94"] == []
    assert witness["intentional_existing_source_alignment"] == {
        tranche.CMC_HISTORICAL_SOURCE.name: {
            "stable_keys": [tranche.CMC_CAMPUS],
            "evidence_keys": [],
        }
    }
    assert witness["cross_source_identity_inference_used"] is False


def test_evidence_cannot_postdate_import(tmp_path: Path) -> None:
    paths = _write_sources(tmp_path)
    connection, _ = tranche.initialize(tmp_path / "atlas.sqlite")
    with pytest.raises(ValueError, match="must not be later"):
        tranche.CuratedOfficialSourceAdapterV11().import_file(
            connection,
            paths[tranche.SOURCE_FILENAMES[1]],
            recorded_at="2026-07-22T03:31:07Z",
        )


def test_private_stage_precedes_barrier_and_withdraws_final_paths() -> None:
    if tranche.ARTIFACT.exists():
        assert tranche.validate_artifact()["curated_source_records"] == 4
        return
    recorded_at = (
        (datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=45))
        .isoformat()
        .replace("+00:00", "Z")
    )
    prepared = tranche._prepare(recorded_at)
    try:
        assert not tranche.ARTIFACT.exists()
        assert all(
            not (tranche.SOURCES_ROOT / name).exists()
            for name in tranche.SOURCE_FILENAMES
        )
        manifest = tranche.validate_artifact(
            prepared.artifact_stage,
            source_paths=tranche._source_paths(prepared.source_stage),
            require_live=False,
            require_frozen=False,
            wall_clock=tranche._instant(recorded_at),
        )
        assert manifest["curated_source_records"] == 4
        tranche._assert_stage_prebarrier(
            [
                prepared.source_stage,
                prepared.artifact_stage,
                *prepared.source_stage.iterdir(),
                *prepared.artifact_stage.iterdir(),
            ],
            recorded_at,
        )
    finally:
        shutil.rmtree(prepared.source_stage)
        shutil.rmtree(prepared.artifact_stage)


def test_partial_final_collision_fails_closed(tmp_path: Path, monkeypatch) -> None:
    sources = tmp_path / "sources"
    sources.mkdir()
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    monkeypatch.setattr(tranche, "SOURCES_ROOT", sources)
    monkeypatch.setattr(tranche, "ARTIFACT", artifact)
    with pytest.raises(tranche.GlobalOfficialGapError, match="partial"):
        tranche.build(recorded_at="2099-01-01T00:00:00Z")


def test_late_promotion_failure_rolls_sources_back_by_identity(
    tmp_path: Path, monkeypatch
) -> None:
    sources_root = tmp_path / "final-sources"
    sources_root.mkdir()
    source_stage = tmp_path / "source-stage"
    source_stage.mkdir()
    for name in tranche.SOURCE_FILENAMES:
        (source_stage / name).write_text(name, encoding="utf-8")
    artifact_stage = tmp_path / "artifact-stage"
    artifact_stage.mkdir()
    (artifact_stage / "member").write_text("member", encoding="utf-8")
    final_artifact = tmp_path / "final-artifact"
    prepared = tranche._Prepared(source_stage, artifact_stage, "2099-01-01T00:00:00Z")
    original = tranche._promote_noreplace

    def fail_on_artifact(source: Path, destination: Path) -> None:
        if source == artifact_stage:
            raise RuntimeError("injected late failure")
        original(source, destination)

    monkeypatch.setattr(tranche, "SOURCES_ROOT", sources_root)
    monkeypatch.setattr(tranche, "ARTIFACT", final_artifact)
    monkeypatch.setattr(tranche, "_freeze_after_barrier", lambda _prepared: None)
    monkeypatch.setattr(tranche, "_promote_noreplace", fail_on_artifact)
    with pytest.raises(RuntimeError, match="injected late failure"):
        tranche._publish(prepared)
    assert not final_artifact.exists()
    assert all(not (sources_root / name).exists() for name in tranche.SOURCE_FILENAMES)
    assert all((source_stage / name).is_file() for name in tranche.SOURCE_FILENAMES)


def test_chronology_rejects_a_future_declared_instant(tmp_path: Path) -> None:
    path = tmp_path / "member"
    path.write_text("x", encoding="utf-8")
    future = (
        (datetime.now(UTC) + timedelta(seconds=10)).isoformat().replace("+00:00", "Z")
    )
    with pytest.raises(tranche.GlobalOfficialGapError, match="predates"):
        tranche._assert_final_ctimes([path], future)


def test_tampered_artifact_fails_validation(tmp_path: Path) -> None:
    if not tranche.ARTIFACT.exists():
        pytest.skip("live immutable artifact not published yet")
    artifact = tmp_path / "artifact"
    shutil.copytree(tranche.ARTIFACT, artifact, copy_function=shutil.copy2)
    artifact.chmod(0o700)
    for member in artifact.iterdir():
        member.chmod(0o600)
    sources = tmp_path / "sources"
    sources.mkdir()
    source_paths = {}
    for name in tranche.SOURCE_FILENAMES:
        destination = sources / name
        shutil.copy2(tranche.SOURCES_ROOT / name, destination)
        destination.chmod(0o600)
        source_paths[name] = destination
    assessment = artifact / "candidate-assessment.json"
    assessment.write_bytes(assessment.read_bytes() + b" ")
    with pytest.raises(tranche.GlobalOfficialGapError, match="canonical|pin"):
        tranche.validate_artifact(
            artifact,
            source_paths=source_paths,
            require_live=False,
            require_frozen=False,
            wall_clock=datetime.now(UTC),
        )


def test_live_artifact_is_frozen_idempotent_and_has_no_residue() -> None:
    if not tranche.ARTIFACT.exists():
        pytest.skip("live immutable artifact not published yet")
    manifest = tranche.validate_artifact()
    assert stat.S_IMODE(tranche.ARTIFACT.stat().st_mode) == 0o555
    assert all(
        stat.S_IMODE((tranche.SOURCES_ROOT / name).stat().st_mode) == 0o444
        for name in tranche.SOURCE_FILENAMES
    )
    assert tranche.build()["status"] == "existing-identical"
    assert manifest["recorded_at"] == tranche.validate_artifact()["recorded_at"]
    assert not tranche.CAPTURE_ORIGIN.exists()
    assert tranche.CAPTURE_TRASH.is_dir()
    assert not tranche.PUBLICATION_LOCK.exists()
    assert list(tranche.SOURCES_ROOT.glob(".global-official-gap-sources.*")) == []
    assert list(tranche.ARTIFACT_ROOT.glob(f".{tranche.ARTIFACT_ID}.*")) == []
