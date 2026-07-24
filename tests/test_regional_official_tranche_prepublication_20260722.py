from __future__ import annotations

import inspect
import json
from pathlib import Path
import shutil
import stat

import pytest

try:
    from datacenter_atlas.datacenter_atlas import (
        regional_official_tranche_prepublication_20260722 as tranche,
    )
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import (  # type: ignore[no-redef]
        regional_official_tranche_prepublication_20260722 as tranche,
    )


RECORDED_AT = "2026-07-22T04:30:00Z"


def _documents() -> dict[str, dict[str, object]]:
    return tranche.expected_source_documents()


def _cleanup(prepared: tranche.PreparedCandidate) -> None:
    if prepared.source_stage.exists():
        shutil.rmtree(prepared.source_stage)
    if prepared.artifact_stage.exists():
        shutil.rmtree(prepared.artifact_stage)


def _configure_private_stages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sources = tmp_path / "sources"
    artifacts = tmp_path / "source_artifacts"
    sources.mkdir()
    artifacts.mkdir()
    monkeypatch.setattr(tranche, "SOURCES_ROOT", sources)
    monkeypatch.setattr(tranche, "ARTIFACT_ROOT", artifacts)
    monkeypatch.setattr(tranche, "PROSPECTIVE_ARTIFACT", artifacts / "candidate")


def test_exact_source_inventory_and_sparse_normalized_output() -> None:
    documents = _documents()
    assert tuple(documents) == tranche.SOURCE_FILENAMES
    assert len(documents) == 3
    assert sum(len(document["evidence"]) for document in documents.values()) == 4
    assert sum(len(document["lifecycle"]) for document in documents.values()) == 3
    for document in documents.values():
        assert document["schema_version"] == "1.1"
        assert document["operating_models"] == []
        assert document["workloads"] == []
        assert document["capacities"] == []
        assert set(document) == {
            "schema_version",
            "evidence",
            "campus",
            "project",
            "lifecycle",
            "operating_models",
            "workloads",
            "capacities",
        }
        for entity in ("campus", "project"):
            assert document[entity]["coordinates"] is None
            assert document[entity]["geometry"] is None


def test_an_khanh_60mw_is_untyped_design_metadata_only() -> None:
    document = _documents()[tranche.AN_KHANH_SOURCE_FILENAME]
    assert document["campus"]["stable_key"] == tranche.AN_KHANH_CAMPUS_KEY
    assert document["project"]["stable_key"] == tranche.AN_KHANH_PROJECT_KEY
    assert document["project"]["address"] == ("An Khanh Commune, Hanoi, Vietnam")
    assert document["campus"]["roles"] == {"developer": ["Viettel"]}
    assert document["project"]["roles"] == {"developer": ["Viettel"]}
    assert document["lifecycle"] == [
        {
            "entity": "project",
            "value": "under_construction",
            "evidence_key": tranche.AN_KHANH_EVIDENCE_KEY,
            "as_of_date": "2025-08-19",
            "method": "authoritative_construction_start",
            "confidence": 0.99,
        }
    ]
    evidence = document["evidence"][0]
    assert evidence["kind"] == "government_record"
    assert evidence["content_hash"] == (
        "e17e5999c45a2341f0aa7986b94a57ab0d05a82615b64e55e353273ccbda63a0"
    )
    assert evidence["metadata"]["design_power_not_normalized"] == {
        "value": 60,
        "unit": "MW",
        "source_wording": "design capacity",
        "typing": "untyped_design_metadata_only",
        "capacity_row_created": False,
        "not_asserted_as": [
            "it_power",
            "grid_power",
            "utility_power",
            "current_power",
            "operational_power",
            "energy_consumption",
        ],
    }
    classification = evidence["metadata"]["classification_metadata_only"]
    assert classification["facility_type_row_created"] is False
    assert classification["workload_row_created"] is False
    assert classification["customer_or_user_role_created"] is False
    assert document["capacities"] == []
    assert document["workloads"] == []


def test_oran_is_cornerstone_only_without_type_workload_roles_or_stage() -> None:
    document = _documents()[tranche.ORAN_SOURCE_FILENAME]
    assert document["campus"]["stable_key"] == tranche.ORAN_CAMPUS_KEY
    assert document["project"]["stable_key"] == tranche.ORAN_PROJECT_KEY
    assert document["project"]["address"] == ("Akid Lotfi District, Oran, Algeria")
    assert document["campus"]["roles"] == {}
    assert document["project"]["roles"] == {}
    assert document["lifecycle"] == [
        {
            "entity": "project",
            "value": "under_construction",
            "evidence_key": tranche.ORAN_RADIO_EVIDENCE_KEY,
            "as_of_date": "2025-03-16",
            "method": "authoritative_construction_start",
            "confidence": 0.99,
        }
    ]
    assert [row["kind"] for row in document["evidence"]] == [
        "government_record",
        "government_record",
    ]
    assert [row["content_hash"] for row in document["evidence"]] == [
        "fc754b5bd44cd345b52f09bdbfb0a8716b947e0c5247a0dec46b1453add64c21",
        "6c543908dfe5ab8517178cee4a8745581bbff916aaa5733f4c58c072d4bda204",
    ]
    radio = next(
        row
        for row in document["evidence"]
        if row["key"] == tranche.ORAN_RADIO_EVIDENCE_KEY
    )
    assert radio["metadata"]["physical_status_as_reported"] == (
        "The cornerstone was laid."
    )
    assert (
        "supports only generic under_construction"
        in radio["metadata"]["stage_guardrail"]
    )
    assert document["operating_models"] == []
    assert document["workloads"] == []
    assert document["capacities"] == []


def test_noor_status_is_retrieval_date_contractor_classification_only() -> None:
    document = _documents()[tranche.NOOR_SOURCE_FILENAME]
    owner = "Arabian Company for Projects & Urban Development"
    assert document["campus"]["stable_key"] == tranche.NOOR_CAMPUS_KEY
    assert document["project"]["stable_key"] == tranche.NOOR_PROJECT_KEY
    assert document["project"]["address"] == "Noor - Capital Gardens, Egypt"
    assert document["campus"]["roles"] == {"owner": [owner]}
    assert document["project"]["roles"] == {
        "owner": [owner],
        "contractor": ["Square Engineering"],
    }
    assert document["lifecycle"] == [
        {
            "entity": "project",
            "value": "under_construction",
            "evidence_key": tranche.NOOR_EVIDENCE_KEY,
            "as_of_date": "2026-07-22",
            "method": "authoritative_physical_status_update",
            "confidence": 0.90,
        }
    ]
    evidence = document["evidence"][0]
    assert evidence["kind"] == "company_disclosure"
    assert evidence["published_at"] is None
    assert evidence["content_hash"] == (
        "809b7b91729c0535105611ce9206678188ffe9bd3281210b04bdc02d7b9be920"
    )
    status = evidence["metadata"]["retrieval_date_status_classification"]
    assert status == {
        "publisher_field": "PROJECT STATUS",
        "publisher_value": "Ongoing",
        "retrieved_at": "2026-07-22T04:21:05Z",
        "normalized_lifecycle": "under_construction",
        "scope": "contractor_current_page_classification_only",
    }
    assert evidence["metadata"]["area_metadata_only"] == {
        "value": 44_220,
        "unit": "square_metres",
        "footprint_or_geometry_claim_created": False,
    }
    assert evidence["metadata"]["schedule_metadata_only"] == {
        "planned_completion_year": 2026,
        "completion_or_operation_claim_created": False,
    }
    assert document["capacities"] == []
    assert document["workloads"] == []


def test_bolivia_is_unhashable_review_only_after_two_timeouts() -> None:
    assessment = tranche._candidate_assessment(RECORDED_AT)
    bolivia = next(
        row
        for row in assessment["candidates"]
        if row["candidate_id"] == "bolivia-fiscalia-data-center"
    )
    assert bolivia["decision"] == ("review_only_unhashable_official_server_timeout")
    assert bolivia["source_paths"] == []
    assert bolivia["stable_key_created"] is False
    assert bolivia["lifecycle_claim_created"] is False
    assert bolivia["evidence_record_created"] is False
    timeout = bolivia["timeout_capture"]
    assert timeout["configured_attempts"] == 2
    assert timeout["completed_timeout_attempts"] == 2
    assert timeout["max_time_seconds_per_attempt"] == 50
    assert timeout["http_status"] is None
    assert timeout["response_header_bytes"] == 0
    assert timeout["response_body_bytes"] == 0
    assert timeout["content_hash"] is None
    assert timeout["headers_sha256"] == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )
    assert all("bolivia" not in name.lower() for name in tranche.SOURCE_FILENAMES)


def test_capture_bundle_is_exact_frozen_private_and_not_redistributed() -> None:
    tranche._validate_capture_directory()
    assert len(tranche.CAPTURES) == 4
    assert len(tranche.CAPTURE_FILE_PINS) == tranche.CAPTURE_FILE_COUNT == 9
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
    assert inventory["controlled_request_target_count"] == 5
    assert inventory["successful_http_200_body_captures"] == 4
    assert inventory["official_server_timeout_targets"] == 1
    assert inventory["raw_capture_redistributed"] is False
    assert inventory["failed_capture"]["body"] is None
    assert inventory["failed_capture"]["headers"]["bytes"] == 0


def test_capture_hash_tamper_fails_closed(tmp_path: Path) -> None:
    copied = tmp_path / "capture"
    shutil.copytree(tranche.CAPTURE_ORIGIN, copied)
    for path in copied.iterdir():
        path.chmod(0o444)
    copied.chmod(0o555)
    tranche._validate_capture_directory(copied)
    copied.chmod(0o755)
    body = copied / "ankhanh.body"
    body.chmod(0o644)
    body.write_bytes(body.read_bytes() + b"\n")
    body.chmod(0o444)
    copied.chmod(0o555)
    with pytest.raises(RuntimeError, match="pin differs"):
        tranche._validate_capture_directory(copied)


def test_v95_collision_witness_is_exact_and_empty() -> None:
    witness = tranche._v95_witness()
    assert witness["v95_release_id"] == "2026-07-22-open-seed-v95"
    assert witness["v95_recorded_at"] == "2026-07-22T04:21:58Z"
    assert witness["v95_selected_input_count"] == 507
    assert witness["v95_entity_count"] == 1_029
    assert witness["v95_public_evidence_count"] == 678
    assert len(witness["planned_stable_keys"]) == 6
    assert len(witness["planned_evidence_keys"]) == 4
    assert len(witness["planned_final_source_paths"]) == 3
    assert witness["planned_stable_key_collisions"] == []
    assert witness["planned_evidence_key_collisions"] == []
    assert witness["planned_selected_source_path_collisions"] == []
    assert (
        witness["v95_pins"]["definition"]["sha256"] == (tranche.V95_DEFINITION_PIN[1])
    )
    assert witness["v95_pins"]["manifest"]["sha256"] == (tranche.V95_MANIFEST_PIN[1])


def test_builder_has_no_publisher_and_builds_private_replayable_stages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_private_stages(tmp_path, monkeypatch)
    assert not hasattr(tranche, "publish")
    assert not hasattr(tranche, "_publish")
    source = inspect.getsource(tranche.prepare_candidate)
    assert "_promote" not in source
    assert "rename" not in source
    assert not tranche.PROSPECTIVE_ARTIFACT.exists()
    assert not any(
        (tranche.SOURCES_ROOT / name).exists() for name in tranche.SOURCE_FILENAMES
    )
    prepared = tranche.prepare_candidate(recorded_at=RECORDED_AT)
    try:
        manifest = tranche.validate_candidate(
            prepared.artifact_stage, prepared.source_stage
        )
        assert manifest["published"] is False
        assert manifest["publisher_function_present"] is False
        assert manifest["curated_source_candidates"] == 3
        assert manifest["review_only_candidates"] == 1
        result = tranche.candidate_result(prepared)
        assert result["status"] == ("PREPUBLICATION_CANDIDATE_BUILT_NOT_PUBLISHED")
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
        snapshot = json.loads(
            (prepared.artifact_stage / "source-snapshot.json").read_text()
        )
        assert snapshot["totals"] == {
            "candidate_assessments": 4,
            "source_records": 3,
            "governed_prepublication_candidates": 3,
            "review_only_candidates": 1,
            "distinct_campuses_in_source_records": 3,
            "projects": 3,
            "distinct_entity_snapshots": 6,
            "new_entities_against_v95": 6,
            "reused_existing_entities": 0,
            "evidence_records": 4,
            "lifecycle_observations": 3,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 0,
            "energy_consumption_observations": 0,
            "facility_type_observations": 0,
            "coordinate_observations": 0,
            "geometry_observations": 0,
            "satellite_observations": 0,
        }
        assert snapshot["integration"]["v96_files_touched"] == []
    finally:
        _cleanup(prepared)


def test_source_and_artifact_tamper_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_private_stages(tmp_path, monkeypatch)
    prepared = tranche.prepare_candidate(recorded_at=RECORDED_AT)
    try:
        source = prepared.source_stage / tranche.AN_KHANH_SOURCE_FILENAME
        source.write_bytes(source.read_bytes() + b"\n")
        with pytest.raises(RuntimeError, match="staged source differs"):
            tranche.validate_candidate(prepared.artifact_stage, prepared.source_stage)
        source.write_bytes(
            tranche._canonical(
                tranche.expected_source_documents()[tranche.AN_KHANH_SOURCE_FILENAME]
            )
        )
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
    (tmp_path / tranche.AN_KHANH_SOURCE_FILENAME).write_text("collision")
    with pytest.raises(RuntimeError, match="prospective final-path collision"):
        tranche.prepare_candidate(recorded_at=RECORDED_AT)
