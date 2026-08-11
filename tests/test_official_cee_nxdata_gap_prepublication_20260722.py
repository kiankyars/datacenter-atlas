from __future__ import annotations

import inspect
import json
from pathlib import Path
import shutil
import stat

import pytest

try:
    from datacenter_atlas.datacenter_atlas import (
        official_cee_nxdata_gap_prepublication_20260722 as tranche,
    )
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import (  # type: ignore[no-redef]
        official_cee_nxdata_gap_prepublication_20260722 as tranche,
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


def test_successor_reuses_exact_identity_and_adds_only_dated_physical_status() -> None:
    document = _document()
    assert document["schema_version"] == "1.1"
    assert document["campus"]["stable_key"] == tranche.CAMPUS_KEY
    assert document["project"]["stable_key"] == tranche.PROJECT_KEY
    assert document["project"]["name"] == "NXDATA-3 / NX-3 / BUH3"
    assert document["project"]["address"] == (
        "38 Bucharest Ring Road, Tunari, Ilfov, Romania"
    )
    assert document["lifecycle"] == [
        {
            "entity": "project",
            "value": "under_construction",
            "evidence_key": tranche.STATUS_EVIDENCE_KEY,
            "as_of_date": "2026-06-02",
            "method": "authoritative_physical_status_update",
            "confidence": 0.99,
        }
    ]
    status = next(
        row for row in document["evidence"] if row["key"] == tranche.STATUS_EVIDENCE_KEY
    )
    assert status["content_hash"] == (
        "223500aa0494aed1c10a6518b1946feb042244390eaf720e0069a12c9c4422f2"
    )
    assert status["published_at"] == "2026-06-02T14:27:57.661Z"
    assert status["metadata"]["physical_status_as_reported"] == [
        "NXDATA-3 is taking shape.",
        "The design is steadily becoming part of the foundation.",
        "NXDATA-3 is helping build that foundation today.",
    ]


def test_metrics_are_exactly_design_stage_and_never_current_consumption() -> None:
    document = _document()
    assert [
        (row["metric"], row["stage"], row["unit"], row["base"])
        for row in document["capacities"]
    ] == [
        ("gross_facility_mw", "design", "MW", 5),
        ("critical_it_mw", "design", "MW", 3),
        ("pue", "design", "ratio", 1.3),
    ]
    assert all(
        row["evidence_key"] == tranche.BROCHURE_EVIDENCE_KEY
        for row in document["capacities"]
    )
    serialized = json.dumps(document, sort_keys=True)
    assert "not current draw" in serialized
    assert "not measured" in serialized
    assert document["operating_models"] == [
        {
            "entity": "project",
            "value": "colocation",
            "evidence_key": tranche.BROCHURE_EVIDENCE_KEY,
            "as_of_date": "2025-07-11",
            "method": "company_disclosure",
            "confidence": 0.99,
        }
    ]
    assert document["workloads"] == []


def test_marketing_opening_and_official_photo_do_not_create_status() -> None:
    document = _document()
    home = next(
        row for row in document["evidence"] if row["key"] == tranche.HOME_EVIDENCE_KEY
    )
    assert home["metadata"]["opening_schedule_only"] == (
        "Estimated site opening Q4 2026."
    )
    assert home["metadata"]["opening_schedule_lifecycle_claim_created"] is False
    assert home["metadata"]["marketing_page_physical_status_claim_created"] is False

    status = next(
        row for row in document["evidence"] if row["key"] == tranche.STATUS_EVIDENCE_KEY
    )
    photo = status["metadata"]["publisher_photo"]
    assert photo["sha256"] == (
        "ea996486ca2b3dbed0a21a9149da4f1c94926e2b61c7685841ca242ee1d20179"
    )
    assert photo["dimensions_px"] == [800, 449]
    assert photo["description_only"] is True
    assert photo["identity_claim_created"] is False
    assert photo["location_claim_created"] is False
    assert photo["lifecycle_claim_created"] is False
    assert photo["capacity_claim_created"] is False
    assert photo["computer_vision_is_construction_truth"] is False
    for entity in ("campus", "project"):
        assert document[entity]["coordinates"] is None
        assert document[entity]["geometry"] is None


def test_porr_waw_and_data4_are_explicit_non_promotions() -> None:
    assessment = tranche._candidate_assessment("2026-07-22T04:40:00Z")
    indexed = {row["candidate_id"]: row for row in assessment["candidates"]}

    nxdata = indexed["nxdata3-buh3"]
    assert nxdata["published"] is False
    assert nxdata["seeded"] is False
    assert nxdata["open_seed_integration"] is False

    anonymous = indexed["porr-anonymous-eighth-february-2025"]
    assert anonymous["decision"] == "review_only_anonymous_identity_unresolved"
    assert anonymous["identity_with_waw_11_1_asserted"] is False
    assert anonymous["identity_with_data4_jawczyce_asserted"] is False
    assert anonymous["current_construction_seed_created"] is False

    waw = indexed["porr-waw-11-1"]
    assert waw["decision"] == "review_only_completed_2022_not_current"
    assert waw["principal_as_reported"] == "Vantage"
    assert waw["construction_runtime_as_reported"] == "2021-03 to 2022-04"
    assert waw["same_asset_as_data4_jawczyce_asserted"] is False

    data4 = indexed["data4-jawczyce-second-data-center"]
    assert data4["decision"] == "review_only_operational_2026_04_09"
    assert data4["official_opening_date"] == "2026-04-09"
    assert data4["identity_with_porr_anonymous_eighth_asserted"] is False
    assert data4["same_asset_as_porr_waw_11_1_asserted"] is False
    assert data4["current_construction_seed_created"] is False


def test_capture_bundle_is_exact_frozen_private_and_records_failed_shortlink() -> None:
    capture = tranche.resolve_external_capture(tranche.CAPTURE_ORIGIN)
    tranche._validate_capture_directory()
    assert len(tranche.CAPTURES) == 13
    assert len(tranche.CAPTURE_FILE_PINS) == tranche.CAPTURE_FILE_COUNT == 26
    assert sum(size for size, _digest in tranche.CAPTURE_FILE_PINS.values()) == (
        tranche.CAPTURE_TOTAL_BYTES
    )
    assert tranche.tree_digest(capture) == tranche.CAPTURE_TREE_SHA256
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o444
        for path in capture.iterdir()
    )
    inventory = tranche._retrieval_inventory("2026-07-22T04:40:00Z")
    assert inventory["normalized_nxdata_claim_capture_count"] == 4
    assert inventory["audit_disposition_capture_count"] == 7
    assert inventory["corroborative_media_capture_count"] == 1
    assert inventory["challenge_capture_count"] == 1
    challenge = next(
        row
        for row in inventory["captures"]
        if row["capture_id"] == "data4_operational_blog_challenge"
    )
    assert challenge["disposition"] == "recaptcha_challenge_not_source_not_used"
    assert inventory["raw_capture_redistributed"] is False


def test_v95_and_accepted_artifact_collision_witness_is_successor_scoped() -> None:
    witness = tranche._collision_witness()
    assert witness["v95_definition"]["curated_input_count"] == 507
    assert witness["v95_release"]["entity_count"] == 1_029
    assert witness["predecessor"]["same_stable_keys_reused"] == [
        tranche.CAMPUS_KEY,
        tranche.PROJECT_KEY,
    ]
    assert witness["predecessor"]["selected_by_v95"] is False
    assert witness["predecessor"]["seeded_by_predecessor_artifact"] is False
    assert witness["successor"]["new_entity_created"] is False
    assert witness["successor"]["new_phase_created"] is False
    assert witness["successor"]["selected_by_v95"] is False
    assert witness["successor"]["v95_release_stable_key_collisions"] == 0
    assert witness["prior_cee_gap_artifact"]["data4_jawczyce_decision"] == (
        "review_only_operational"
    )


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

    prepared = tranche.prepare_candidate(recorded_at="2026-07-22T04:40:00Z")
    try:
        manifest = tranche.validate_candidate(
            prepared.artifact_stage, prepared.source_stage
        )
        assert manifest["published"] is False
        assert manifest["publisher_function_present"] is False
        assert manifest["curated_source_candidates"] == 1
        assert manifest["review_only_candidates"] == 3
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
        snapshot = json.loads(
            (prepared.artifact_stage / "source-snapshot.json").read_text()
        )
        assert snapshot["totals"]["source_records"] == 1
        assert snapshot["totals"]["evidence_records"] == 4
        assert snapshot["totals"]["lifecycle_observations"] == 1
        assert snapshot["totals"]["capacity_estimates"] == 3
        assert snapshot["totals"]["design_capacity_estimates"] == 3
        assert snapshot["totals"]["computer_vision_normalized_claims"] == 0
        assert snapshot["totals"]["energy_consumption_observations"] == 0
        assert snapshot["integration"]["v95_mutated"] is False
    finally:
        _cleanup(prepared)


def test_source_and_artifact_tamper_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_private_candidate_roots(tmp_path, monkeypatch)
    prepared = tranche.prepare_candidate(recorded_at="2026-07-22T04:40:00Z")
    try:
        source = prepared.source_stage / tranche.SOURCE_FILENAME
        source.write_bytes(source.read_bytes() + b"\n")
        with pytest.raises(RuntimeError, match="staged source differs"):
            tranche.validate_candidate(prepared.artifact_stage, prepared.source_stage)
        source.write_bytes(tranche._canonical(tranche.expected_source_document()))
        assessment = prepared.artifact_stage / "candidate-assessment.json"
        assessment.write_bytes(assessment.read_bytes() + b" ")
        with pytest.raises(RuntimeError, match="candidate manifest pin differs"):
            tranche.validate_candidate(prepared.artifact_stage, prepared.source_stage)
    finally:
        _cleanup(prepared)


def test_prospective_final_collision_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tranche, "SOURCES_ROOT", tmp_path)
    monkeypatch.setattr(tranche, "ARTIFACT_ROOT", tmp_path)
    monkeypatch.setattr(tranche, "PROSPECTIVE_ARTIFACT", tmp_path / "artifact")
    monkeypatch.setattr(tranche, "PROSPECTIVE_SOURCE", tmp_path / "source.json")
    tranche.PROSPECTIVE_SOURCE.write_text("collision")
    with pytest.raises(RuntimeError, match="prospective final-path collision"):
        tranche.prepare_candidate(recorded_at="2026-07-22T04:40:00Z")
