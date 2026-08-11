from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import shutil

import pytest

try:
    from datacenter_atlas.datacenter_atlas import (
        google_official_haskell_maize_pyramid_current_build_gap_20260722 as tranche,
    )
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import (  # type: ignore[no-redef]
        google_official_haskell_maize_pyramid_current_build_gap_20260722 as tranche,
    )


def test_exact_three_source_contract_and_lifecycle_rows() -> None:
    documents = tranche.expected_source_documents()
    assert tuple(documents) == tranche.SOURCE_FILENAMES
    assert len(documents) == 3
    assert sum(len(document["evidence"]) for document in documents.values()) == 8
    assert len(
        {
            evidence["key"]
            for document in documents.values()
            for evidence in document["evidence"]
        }
    ) == 8
    lifecycle = {
        (
            document["project"]["stable_key"],
            document["lifecycle"][0]["value"],
            document["lifecycle"][0]["as_of_date"],
        )
        for document in documents.values()
    }
    assert lifecycle == {
        (
            "curated:google-haskell-county-quantum-linked-data-center-campus:current-development",
            "under_construction",
            "2025-11-30",
        ),
        (
            "curated:google-michigan-city-project-maize-data-center:2025-site-works",
            "site_preparation",
            "2025-09-24",
        ),
        (
            "curated:google-west-memphis-project-pyramid-data-center-campus:current-development",
            "under_construction",
            "2025-10-02",
        ),
    }
    for document in documents.values():
        assert document["capacities"] == []
        assert document["operating_models"] == []
        assert document["workloads"] == []
        for entity in ("campus", "project"):
            assert document[entity]["roles"] == {}
            assert document[entity]["coordinates"] is None
            assert document[entity]["geometry"] is None


def test_haskell_is_one_pair_with_month_precision_and_supply_metadata_only() -> None:
    document = tranche.expected_source_documents()[tranche.SITES[0].filename]
    assert document["campus"]["stable_key"].endswith(
        "quantum-linked-data-center-campus"
    )
    construction = next(
        row
        for row in document["evidence"]
        if row["key"] == "google-haskell-county-construction-start-2025-11"
    )
    assert construction["metadata"]["status_date_precision"] == "month"
    assert "does not claim an event" in construction["metadata"][
        "month_end_as_of_basis"
    ]
    quantum = next(
        row
        for row in document["evidence"]
        if row["key"]
        == "intersect-quantum-google-colocation-observed-2026-07-22"
    )
    supply = quantum["metadata"]["energy_supply_metadata"]
    assert supply["solar_generation_nameplate_mw"] == 640
    assert supply["battery_storage_energy_gwh"] == 1.3
    assert "neither value is data-center" in supply["normalization"]
    assessment = tranche._candidate_assessment("2026-07-22T03:00:00Z")
    candidate = assessment["candidates"][0]
    assert "THM and Journey" in candidate["identity_limit"]
    assert candidate["normalized_capacity"] is None
    assert candidate["lifecycle"]["source_date_precision"] == "month"


def test_maize_keeps_site_works_separate_from_later_google_identity() -> None:
    document = tranche.expected_source_documents()[tranche.SITES[1].filename]
    assert document["campus"]["address"].startswith("402 Royal Road")
    assert document["campus"]["as_of_date"] == "2026-04-16"
    assert document["lifecycle"][0]["as_of_date"] == "2025-09-24"
    assert document["lifecycle"][0]["value"] == "site_preparation"
    assessment = tranche._candidate_assessment("2026-07-22T03:00:00Z")
    candidate = assessment["candidates"][1]
    assert candidate["identity_join"]["google_ownership_not_backdated"] is True
    assert candidate["normalized_capacity"] is None
    idem = next(
        row
        for row in document["evidence"]
        if row["key"] == "idem-project-maize-site-works-inspection-2025-09-24"
    )
    assert "no vertical" in idem["metadata"]["stage_scope"]


def test_pyramid_uses_aedc_status_serc_identity_and_omits_usace_facts() -> None:
    document = tranche.expected_source_documents()[tranche.SITES[2].filename]
    serialized = json.dumps(document, sort_keys=True).casefold()
    assert "500/230" not in serialized
    assert "latitude" not in serialized
    assert "longitude" not in serialized
    assert "voltage_kv" not in serialized
    assert document["lifecycle"][0]["evidence_key"] == (
        "arkansas-google-west-memphis-construction-2025-10-02"
    )
    assert document["project"]["evidence_key"] == (
        "serc-project-pyramid-google-west-memphis-identity-2026-06-24"
    )
    assessment = tranche._candidate_assessment("2026-07-22T03:00:00Z")
    candidate = assessment["candidates"][2]
    assert candidate["coordinate"] is None
    assert candidate["voltage_metadata"] is None
    assert "returned HTTP 403" in candidate["usace_omission"]
    assert "every MW figure" in candidate["serc_scope"]


def test_review_only_notes_are_exactly_spade_pine_island_and_hermantown() -> None:
    assessment = tranche._candidate_assessment("2026-07-22T03:00:00Z")
    assert assessment["candidate_count"] == 6
    assert assessment["seed_eligible_source_record_count"] == 3
    assert assessment["review_only_count"] == 3
    assert [row["candidate_id"] for row in assessment["candidates"][3:]] == [
        "google-new-florence-project-spade",
        "google-pine-island-project-skyway",
        "google-hermantown-potential-campus",
    ]
    assert all("body_sha256" in row for row in assessment["candidates"][3:])


def test_v91_collision_witness_is_absent_and_pinned() -> None:
    witness = tranche._collision_witness(tranche.expected_source_documents())
    assert witness["v91_selected_input_count"] == 480
    assert witness["v91_entity_count"] == 978
    assert witness["planned_distinct_stable_keys"] == 6
    assert witness["planned_distinct_evidence_keys"] == 8
    assert witness["exact_v91_stable_key_collisions"] == []
    assert witness["exact_v91_evidence_key_collisions"] == []
    assert witness["exact_v91_haskell_quantum_matches"] == []
    assert witness["exact_v91_project_maize_matches"] == []
    assert witness["exact_v91_project_pyramid_matches"] == []


def test_capture_set_includes_eleven_successes_and_three_pinned_failures() -> None:
    directory = (
        tranche.resolve_external_capture(tranche.CAPTURE_ORIGIN, tranche.CAPTURE_TRASH)
    )
    tranche._validate_capture_directory(directory)
    assert len(tranche.CAPTURES) == 14
    assert len(tranche.CAPTURE_FILE_PINS) == 28
    assert sum(capture.http_status == 200 for capture in tranche.CAPTURES) == 11
    assert [
        capture.http_status
        for capture in tranche.CAPTURES
        if capture.http_status != 200
    ] == [403, 403, 401]
    assert sum(
        size for size, _digest in tranche.CAPTURE_FILE_PINS.values()
    ) == tranche.CAPTURE_TOTAL_BYTES


def test_private_stage_replays_offline_and_has_no_final_path_side_effect() -> None:
    if tranche.ARTIFACT.exists():
        manifest = tranche.validate_artifact()
        assert manifest["curated_source_records"] == 3
        return
    recorded_at = (
        datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=45)
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
        assert manifest["review_only_candidates"] == 3
        assert manifest["successful_http_200_body_captures"] == 11
        assert manifest["failed_http_body_captures"] == 3
        snapshot = json.loads(
            (prepared.artifact_stage / "source-snapshot.json").read_text()
        )
        assert snapshot["totals"]["new_entities_against_v91"] == 6
        assert snapshot["totals"]["unique_imported_entity_snapshots"] == 6
        assert snapshot["integration"]["open_seed_v92_touched"] is False
        for key in (
            "capacity_estimates",
            "normalized_critical_it_mw_sum",
            "annual_energy_estimates",
            "pue_estimates",
            "wue_estimates",
            "coordinates_present",
            "geometry_present",
            "voltage_metadata_records",
        ):
            assert snapshot["totals"][key] == 0
    finally:
        if prepared.source_stage.exists():
            shutil.rmtree(prepared.source_stage)
        if prepared.artifact_stage.exists():
            prepared.artifact_stage.chmod(0o700)
            shutil.rmtree(prepared.artifact_stage)


def test_expected_documents_and_artifact_payloads_are_deterministic() -> None:
    first = tranche.expected_source_documents()
    second = tranche.expected_source_documents()
    assert first == second
    assert tranche._artifact_documents("2026-07-22T03:00:00Z", first) == (
        tranche._artifact_documents("2026-07-22T03:00:00Z", second)
    )


def test_partial_final_collision_fails_closed(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(tranche, "SOURCES_ROOT", tmp_path)
    monkeypatch.setattr(tranche, "ARTIFACT", tmp_path / "artifact")
    (tmp_path / tranche.SOURCE_FILENAMES[0]).write_text("collision")
    with pytest.raises(
        RuntimeError,
        match="partial Google Haskell/Maize/Pyramid final-path collision",
    ):
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
    tranche._write_artifact_stage(
        artifact_stage, "2099-01-01T00:00:00Z", documents
    )
    monkeypatch.setattr(tranche, "SOURCES_ROOT", source_root)
    monkeypatch.setattr(tranche, "ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr(tranche, "ARTIFACT", artifact_root / tranche.ARTIFACT_ID)
    prepared = tranche._Prepared(
        source_stage, artifact_stage, "2099-01-01T00:00:00Z"
    )
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
