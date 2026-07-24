from __future__ import annotations

import inspect
import json
from pathlib import Path
import shutil
import stat

import pytest

try:
    from datacenter_atlas.datacenter_atlas import (
        edgeconnex_lambda_chicago_official_gap_prepublication_20260722 as tranche,
    )
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import (  # type: ignore[no-redef]
        edgeconnex_lambda_chicago_official_gap_prepublication_20260722 as tranche,
    )


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


def test_chicago_status_is_last_observed_and_23mw_remains_untyped() -> None:
    document = _document()
    assert document["schema_version"] == "1.1"
    assert document["campus"]["stable_key"] == tranche.CAMPUS_KEY
    assert document["project"]["stable_key"] == tranche.PROJECT_KEY
    assert document["lifecycle"] == [
        {
            "entity": "project",
            "value": "under_construction",
            "evidence_key": tranche.STATUS_EVIDENCE_KEY,
            "as_of_date": "2025-08-21",
            "method": "authoritative_physical_status_update",
            "confidence": 0.98,
        }
    ]
    assert document["capacities"] == []
    status = next(
        row for row in document["evidence"] if row["key"] == tranche.STATUS_EVIDENCE_KEY
    )
    metadata = status["metadata"]
    assert metadata["reported_chicago_value_mw"] == 23
    assert metadata["reported_chicago_value_type"] == "untyped"
    assert "current consumption" in metadata["capacity_guardrail"]
    assert "last-observed" in metadata["currentness_scope"]
    assert metadata["forecast_as_reported"] == "Ready for Service in 2026"


def test_lambda_roles_and_intended_workloads_are_exactly_entity_scoped() -> None:
    document = _document()
    expected_roles = {"developer": ["EdgeConneX"], "tenant": ["Lambda"]}
    assert document["campus"]["roles"] == expected_roles
    assert document["project"]["roles"] == expected_roles
    assert [row["value"] for row in document["workloads"]] == [
        "hpc",
        "ai_training",
        "ai_inference",
    ]
    assert all(row["entity"] == "project" for row in document["workloads"])
    assert document["operating_models"] == []
    serialized = json.dumps(document, sort_keys=True)
    assert "installed accelerators" in serialized
    assert "No schema operating model is inferred" in serialized


def test_safety_week_and_chi03_are_corroboration_and_non_identity_only() -> None:
    document = _document()
    safety = next(
        row for row in document["evidence"] if row["key"] == tranche.SAFETY_EVIDENCE_KEY
    )
    assert safety["metadata"]["identity_bridge_created"] is False
    assert safety["metadata"]["lifecycle_observation_created"] is False
    assert safety["metadata"]["site_list_as_reported"] == [
        "Atlanta",
        "Amsterdam",
        "Chicago",
        "Cyberjaya",
        "Dublin",
        "Frankfurt",
        "Jakarta",
        "Santiago",
    ]
    location = next(
        row
        for row in document["evidence"]
        if row["key"] == tranche.LOCATION_EVIDENCE_KEY
    )
    assert location["metadata"]["reported_chi03_value_mw"] == 22.4
    assert "does not connect Lambda" in location["metadata"]["identity_guardrail"]
    assert all(
        row["evidence_key"] == tranche.STATUS_EVIDENCE_KEY
        for row in document["lifecycle"]
    )
    for entity in ("campus", "project"):
        assert document[entity]["coordinates"] is None
        assert document[entity]["geometry"] is None


def test_other_edgeconnex_sites_are_explicit_review_only_non_promotions() -> None:
    assessment = tranche._candidate_assessment("2026-07-22T05:10:00Z")
    indexed = {row["candidate_id"]: row for row in assessment["candidates"]}
    assert assessment["totals"] == {
        "candidates": 10,
        "governed_prepublication_candidates": 1,
        "review_only_candidates": 9,
        "published": 0,
        "seeded": 0,
    }
    assert indexed["edgeconnex-cyberjaya-initial-campus"]["decision"] == (
        "review_only_stale_status_and_elapsed_forecast"
    )
    assert (
        indexed["edgeconnex-frankfurt-unspecified-site"]["current_emea_index_status"]
        == "coming-soon"
    )
    assert indexed["edgeconnex-dublin-unspecified-site"]["current_page_reports"] == (
        "two operational data centers, land bank, and DUB03 planned"
    )
    assert (
        indexed["edgeconnex-jakarta-unspecified-expansion"]["current_page_reports"]
        == "2 MW operational and land banked expansion"
    )
    assert all(
        row.get("current_construction_seed_created") is False
        for row in assessment["candidates"][1:]
    )


def test_capture_bundle_is_exact_frozen_private_first_party_only() -> None:
    tranche._validate_capture_directory()
    assert len(tranche.CAPTURES) == 14
    assert len(tranche.CAPTURE_FILE_PINS) == tranche.CAPTURE_FILE_COUNT == 28
    assert sum(size for size, _digest in tranche.CAPTURE_FILE_PINS.values()) == (
        tranche.CAPTURE_TOTAL_BYTES
    )
    assert tranche.tree_digest(tranche.CAPTURE_ORIGIN) == (tranche.CAPTURE_TREE_SHA256)
    assert stat.S_IMODE(tranche.CAPTURE_ORIGIN.stat().st_mode) == 0o555
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o444
        for path in tranche.CAPTURE_ORIGIN.iterdir()
    )
    inventory = tranche._retrieval_inventory("2026-07-22T05:10:00Z")
    assert inventory["first_party_only"] is True
    assert inventory["capture_count"] == 14
    assert inventory["raw_capture_redistributed"] is False
    assert inventory["credentials_supplied"] is False


def test_v95_and_later_source_collision_witness_is_clean() -> None:
    witness = tranche._collision_witness()
    assert witness["v95_definition"]["curated_input_count"] == 507
    assert witness["v95_release"]["entity_count"] == 1_029
    assert witness["v95_selected_edgeconnex_sources"] == [
        "sources/curated-official-2026-07-17.json",
        "sources/curated-official-2026-07-19-edgeconnex-greater-osaka.json",
    ]
    assert witness["v95_source_stable_key_collisions"] == []
    assert witness["v95_source_url_collisions"] == []
    assert witness["later_source_stable_key_collisions"] == []
    assert witness["later_source_url_collisions"] == []
    assert witness["chi03_identity_asserted"] is False
    assert witness["edged_chicago_identity_asserted"] is False
    assert witness["new_entity_candidate_count"] == 2


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

    prepared = tranche.prepare_candidate(recorded_at="2026-07-22T05:10:00Z")
    try:
        manifest = tranche.validate_candidate(
            prepared.artifact_stage, prepared.source_stage
        )
        assert manifest["published"] is False
        assert manifest["publisher_function_present"] is False
        assert manifest["curated_source_candidates"] == 1
        assert manifest["review_only_candidates"] == 9
        result = tranche.candidate_result(prepared)
        assert result["status"] == "PREPUBLICATION_CANDIDATE_BUILT_NOT_PUBLISHED"
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
    first = tranche.prepare_candidate(recorded_at="2026-07-22T05:10:00Z")
    second = tranche.prepare_candidate(recorded_at="2026-07-22T05:10:00Z")
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
    before = sorted(path.name for path in tranche.SOURCES_ROOT.iterdir())
    with pytest.raises(RuntimeError, match="prospective final-path collision"):
        tranche.prepare_candidate(recorded_at="2026-07-22T05:10:00Z")
    assert sorted(path.name for path in tranche.SOURCES_ROOT.iterdir()) == before
    assert list(tranche.ARTIFACT_ROOT.iterdir()) == []


def test_candidate_artifact_contains_no_private_path_or_raw_response_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_private_candidate_roots(tmp_path, monkeypatch)
    prepared = tranche.prepare_candidate(recorded_at="2026-07-22T05:10:00Z")
    try:
        combined = b"\n".join(
            path.read_bytes() for path in sorted(prepared.artifact_stage.iterdir())
        )
        assert b"/private/" not in combined
        assert b"/Users/" not in combined
        assert b"<html" not in combined.lower()
        rights = json.loads(
            (prepared.artifact_stage / "rights-and-disposition.json").read_text(
                encoding="utf-8"
            )
        )
        assert rights["raw_capture_redistributed"] is False
        assert rights["raw_response_bodies_retained_in_artifact"] is False
        assert rights["private_capture_bundle_id"] == tranche.CAPTURE_BUNDLE_ID
    finally:
        _cleanup(prepared)


def test_capture_tamper_is_rejected_without_touching_frozen_origin(
    tmp_path: Path,
) -> None:
    copy = tmp_path / "capture"
    shutil.copytree(tranche.CAPTURE_ORIGIN, copy)
    copy.chmod(0o555)
    for path in copy.iterdir():
        path.chmod(0o444)
    victim = copy / "chicago_lambda.body"
    victim.chmod(0o644)
    victim.write_bytes(victim.read_bytes() + b"x")
    victim.chmod(0o444)
    with pytest.raises(RuntimeError, match="frozen dependency differs"):
        tranche._validate_capture_directory(copy)
    tranche._validate_capture_directory()
