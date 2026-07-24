from __future__ import annotations

import inspect
import json
from pathlib import Path
import shutil
import stat

import pytest

try:
    from datacenter_atlas.datacenter_atlas import (
        africa_central_asia_official_gap_prepublication_20260722 as tranche,
    )
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import (  # type: ignore[no-redef]
        africa_central_asia_official_gap_prepublication_20260722 as tranche,
    )


RECORDED_AT = "2026-07-22T05:46:30Z"


def _document() -> dict[str, object]:
    return tranche.expected_source_document()


def _cleanup(prepared: tranche.PreparedCandidate) -> None:
    if prepared.source_stage.exists():
        shutil.rmtree(prepared.source_stage)
    if prepared.artifact_stage.exists():
        shutil.rmtree(prepared.artifact_stage)


def _configure_private_candidate_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources = tmp_path / "sources"
    artifacts = tmp_path / "source_artifacts"
    sources.mkdir()
    artifacts.mkdir()
    monkeypatch.setattr(tranche, "SOURCES_ROOT", sources)
    monkeypatch.setattr(tranche, "ARTIFACT_ROOT", artifacts)
    monkeypatch.setattr(
        tranche, "PROSPECTIVE_SOURCE", sources / tranche.SOURCE_FILENAME
    )
    monkeypatch.setattr(
        tranche, "PROSPECTIVE_ARTIFACT", artifacts / tranche.ARTIFACT_ID
    )


def test_dushanbe_is_exact_review_identity_with_no_data_center_lifecycle() -> None:
    document = _document()
    assert document["schema_version"] == "1.1"
    assert document["campus"]["stable_key"] == tranche.CAMPUS_KEY
    assert document["project"]["stable_key"] == tranche.PROJECT_KEY
    assert document["campus"]["address"] == "Dushanbe, Tajikistan"
    assert document["project"]["address"] == "Dushanbe, Tajikistan"
    assert document["campus"]["roles"] == {}
    assert document["project"]["roles"] == {}
    assert document["lifecycle"] == []
    assert document["capacities"] == []
    assert document["workloads"] == []
    assert document["operating_models"] == []
    for entity in ("campus", "project"):
        assert document[entity]["coordinates"] is None
        assert document[entity]["geometry"] is None


def test_component_scope_guardrail_blocks_mixed_use_groundbreaking_promotion() -> None:
    evidence = _document()["evidence"][0]
    metadata = evidence["metadata"]
    assert metadata["complex_component_count_as_reported"] == 4
    assert (
        "advanced computing infrastructure"
        in (metadata["data_center_component_as_reported"])
    )
    assert (
        "full four-object mixed-use complex" in (metadata["component_phase_guardrail"])
    )
    assert "No data-center lifecycle observation" in metadata["lifecycle_guardrail"]
    assert metadata["current_construction_seed_created"] is False
    assert metadata["complex_investment_usd_as_reported"] == 100_000_000
    assert metadata["complex_construction_area_sqm_as_reported"] == 53_000
    assert "not allocated to the data center" in metadata["capacity_energy_guardrail"]


def test_assessment_closes_with_zero_governed_candidates() -> None:
    assessment = tranche._candidate_assessment(RECORDED_AT)
    indexed = {row["candidate_id"]: row for row in assessment["candidates"]}
    assert assessment["totals"] == {
        "screened_signals": 9,
        "governed_prepublication_candidates": 0,
        "review_only_absent_signals": 8,
        "already_covered_in_v96": 1,
        "published": 0,
        "seeded": 0,
    }
    assert (
        indexed["it-hub-dushanbe-regional-ai-center-data-center-component"]["decision"]
        == "review_only_mixed_use_component_phase_ambiguous"
    )
    assert (
        indexed["kazakhstan-jmot04-ample-50-to-200mw"]["normalized_capacity_rows"] == 0
    )
    assert (
        indexed["wingu-dar-es-salaam-capacity-expansion"][
            "named_active_construction_phase"
        ]
        is False
    )
    assert (
        indexed["paix-jib1-djibouti"]["current_location_route_effective_url"]
        == "https://www.paix.io/contact-us"
    )
    assert indexed["kasi-los1-lekki"]["decision"] == (
        "already_covered_in_v96_commissioning_not_a_gap"
    )


def test_capture_bundle_is_exact_frozen_private_first_party_only() -> None:
    tranche._validate_capture_directory()
    assert len(tranche.CAPTURES) == 10
    assert len(tranche.CAPTURE_FILE_PINS) == tranche.CAPTURE_FILE_COUNT == 30
    assert sum(size for size, _digest in tranche.CAPTURE_FILE_PINS.values()) == (
        tranche.CAPTURE_TOTAL_BYTES
    )
    assert tranche.tree_digest(tranche.CAPTURE_ORIGIN) == (tranche.CAPTURE_TREE_SHA256)
    assert stat.S_IMODE(tranche.CAPTURE_ORIGIN.stat().st_mode) == 0o555
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o444
        for path in tranche.CAPTURE_ORIGIN.iterdir()
    )
    inventory = tranche._retrieval_inventory(RECORDED_AT)
    assert inventory["first_party_only"] is True
    assert inventory["capture_count"] == 10
    assert inventory["raw_capture_redistributed"] is False
    assert inventory["credentials_supplied"] is False
    assert inventory["captures"][0]["retrieved_at"] == "2026-07-22T05:39:14Z"


def test_v96_and_later_collision_witness_is_clean_and_kasi_is_covered() -> None:
    witness = tranche._collision_witness()
    assert witness["v96_definition"]["curated_input_count"] == 516
    assert witness["v96_release"]["entity_count"] == 1_047
    assert witness["v96_release"]["evidence_count"] == 690
    assert witness["v96_source_stable_key_collisions"] == []
    assert witness["v96_source_url_collisions"] == []
    assert witness["later_source_stable_key_collisions"] == []
    assert witness["later_source_url_collisions"] == []
    assert witness["new_seed_eligible_entity_count"] == 0
    assert {row["status"] for row in witness["kasi_v96_rows"]} == {
        "",
        "commissioning",
    }


def test_builder_has_no_publisher_and_builds_private_replayable_stages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_private_candidate_roots(tmp_path, monkeypatch)
    assert not hasattr(tranche, "publish")
    assert not hasattr(tranche, "_publish")
    source = inspect.getsource(tranche.prepare_candidate)
    assert "_promote" not in source
    assert "rename" not in source
    assert not tranche.PROSPECTIVE_ARTIFACT.exists()
    assert not tranche.PROSPECTIVE_SOURCE.exists()

    prepared = tranche.prepare_candidate(recorded_at=RECORDED_AT)
    try:
        manifest = tranche.validate_candidate(
            prepared.artifact_stage, prepared.source_stage
        )
        assert manifest["published"] is False
        assert manifest["publisher_function_present"] is False
        assert manifest["review_source_records"] == 1
        assert manifest["governed_prepublication_candidates"] == 0
        assert manifest["review_only_absent_signals"] == 8
        result = tranche.candidate_result(prepared)
        assert result["status"] == ("PREPUBLICATION_REVIEW_CARRIER_BUILT_NOT_PUBLISHED")
        assert result["published"] is False
        assert result["prospective_final_artifact_exists"] is False
        assert result["prospective_final_source_exists"] is False
        assert stat.S_IMODE(prepared.source_stage.stat().st_mode) == 0o700
        assert stat.S_IMODE(prepared.artifact_stage.stat().st_mode) == 0o700
        assert all(
            stat.S_IMODE(path.stat().st_mode) == 0o600
            for path in prepared.source_stage.iterdir()
        )
        assert all(
            stat.S_IMODE(path.stat().st_mode) == 0o600
            for path in prepared.artifact_stage.iterdir()
        )
    finally:
        _cleanup(prepared)


def test_two_fixed_prepublication_replays_are_byte_identical_and_unique(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_private_candidate_roots(tmp_path, monkeypatch)
    first = tranche.prepare_candidate(recorded_at=RECORDED_AT)
    second = tranche.prepare_candidate(recorded_at=RECORDED_AT)
    try:
        assert first.source_stage != second.source_stage
        assert first.artifact_stage != second.artifact_stage
        assert (first.source_stage / tranche.SOURCE_FILENAME).read_bytes() == (
            second.source_stage / tranche.SOURCE_FILENAME
        ).read_bytes()
        assert tranche.tree_digest(first.artifact_stage) == tranche.tree_digest(
            second.artifact_stage
        )
    finally:
        _cleanup(first)
        _cleanup(second)


def test_final_path_collision_fails_closed_before_any_stage_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_private_candidate_roots(tmp_path, monkeypatch)
    tranche.PROSPECTIVE_SOURCE.write_text("occupied\n", encoding="utf-8")
    before_sources = sorted(path.name for path in tranche.SOURCES_ROOT.iterdir())
    before_artifacts = sorted(path.name for path in tranche.ARTIFACT_ROOT.iterdir())
    with pytest.raises(RuntimeError, match="prospective final-path collision"):
        tranche.prepare_candidate(recorded_at=RECORDED_AT)
    assert (
        sorted(path.name for path in tranche.SOURCES_ROOT.iterdir()) == before_sources
    )
    assert (
        sorted(path.name for path in tranche.ARTIFACT_ROOT.iterdir())
        == before_artifacts
    )


def test_artifact_contains_no_private_path_or_raw_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_private_candidate_roots(tmp_path, monkeypatch)
    prepared = tranche.prepare_candidate(recorded_at=RECORDED_AT)
    try:
        serialized = b"".join(
            path.read_bytes() for path in prepared.artifact_stage.iterdir()
        )
        assert b"/Users/" not in serialized
        assert b"/private/" not in serialized
        assert tranche.CAPTURE_ORIGIN.name.encode() in serialized
        assert tranche.CAPTURE_ORIGIN.as_posix().encode() not in serialized
        assert b'raw_capture_redistributed": false' in serialized
    finally:
        _cleanup(prepared)


def test_manifest_tamper_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_private_candidate_roots(tmp_path, monkeypatch)
    prepared = tranche.prepare_candidate(recorded_at=RECORDED_AT)
    try:
        assessment = prepared.artifact_stage / "candidate-assessment.json"
        assessment.write_bytes(b"{}\n")
        with pytest.raises(RuntimeError, match="candidate manifest pin differs"):
            tranche.validate_candidate(prepared.artifact_stage, prepared.source_stage)
    finally:
        _cleanup(prepared)


def test_source_document_has_no_hidden_capacity_or_type_normalization() -> None:
    document = _document()
    serialized = json.dumps(document, sort_keys=True)
    assert '"capacities": []' in serialized
    assert '"workloads": []' in serialized
    assert '"operating_models": []' in serialized
    assert "critical_it_mw" not in serialized
    assert "gross_facility_mw" not in serialized
    assert 'ai_training"' not in serialized
    assert 'ai_inference"' not in serialized
