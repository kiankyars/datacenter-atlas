from __future__ import annotations

import inspect
import json
import shutil
import socket
import stat
from pathlib import Path

import pytest

try:
    from datacenter_atlas.datacenter_atlas import (
        official_humboldt_chesterfield_gap_prepublication_20260724 as tranche,
    )
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import (  # type: ignore[no-redef]
        official_humboldt_chesterfield_gap_prepublication_20260724 as tranche,
    )


RECORDED_AT = "2026-07-24T21:20:00Z"


def _documents() -> dict[str, dict[str, object]]:
    return tranche.expected_source_documents()


def _cleanup(prepared: tranche.PreparedCandidate) -> None:
    if prepared.source_stage.exists():
        shutil.rmtree(prepared.source_stage)
    if prepared.artifact_stage.exists():
        shutil.rmtree(prepared.artifact_stage)


def _configure_private_stages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    sources = tmp_path / "sources"
    artifacts = tmp_path / "source_artifacts"
    sources.mkdir()
    artifacts.mkdir()
    monkeypatch.setattr(tranche, "SOURCES_ROOT", sources)
    monkeypatch.setattr(tranche, "ARTIFACT_ROOT", artifacts)
    monkeypatch.setattr(
        tranche,
        "PROSPECTIVE_ARTIFACT",
        artifacts / tranche.ARTIFACT_ID,
    )
    return sources, artifacts


def test_exact_four_source_documents_and_sparse_normalized_output() -> None:
    documents = _documents()
    assert tuple(documents) == tranche.SOURCE_FILENAMES
    assert len(documents) == 4
    assert sum(len(row["evidence"]) for row in documents.values()) == 10
    assert sum(len(row["lifecycle"]) for row in documents.values()) == 5
    assert sum(len(row["workloads"]) for row in documents.values()) == 1
    assert sum(len(row["capacities"]) for row in documents.values()) == 1
    for document in documents.values():
        assert document["schema_version"] == "1.1"
        assert document["operating_models"] == []
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
        for entity_name in ("campus", "project"):
            entity = document[entity_name]
            assert entity["coordinates"] is None
            assert entity["geometry"] is None


def test_humboldt_is_one_unknown_party_pair_with_conservative_15mw() -> None:
    document = _documents()[tranche.HUMBOLDT_SOURCE_FILENAME]
    assert document["campus"]["stable_key"] == tranche.HUMBOLDT_CAMPUS_KEY
    assert document["project"]["stable_key"] == tranche.HUMBOLDT_PROJECT_KEY
    assert document["campus"]["roles"] == {}
    assert document["project"]["roles"] == {}
    assert document["lifecycle"] == [
        {
            "entity": "project",
            "value": "under_construction",
            "evidence_key": tranche.HUMBOLDT_EVIDENCE_KEY,
            "as_of_date": "2026-07-23",
            "method": "authoritative_physical_status_update",
            "confidence": 0.99,
        }
    ]
    assert document["workloads"] == [
        {
            "entity": "project",
            "value": "crypto_mining",
            "evidence_key": tranche.HUMBOLDT_EVIDENCE_KEY,
            "as_of_date": "2026-07-23",
            "method": "government_record",
            "confidence": 0.99,
        }
    ]
    capacity = document["capacities"][0]
    assert capacity["metric"] == "gross_facility_mw"
    assert capacity["stage"] == "planned"
    assert (capacity["low"], capacity["base"], capacity["high"]) == (15, 15, 15)
    assert "not critical IT" in capacity["notes"]
    assert "current draw" in capacity["notes"]
    assert "annual energy" in capacity["notes"]
    assert "generation" in capacity["notes"]

    evidence = document["evidence"][0]
    metadata = evidence["metadata"]
    assert metadata["reported_customer_facility_load_mw"] == 15
    assert metadata["reported_application"] == "cryptocurrency mining"
    assert metadata["reported_annual_water_use_gallons_up_to_approximate"] == (
        2_000_000
    )
    assert metadata["developer"] is None
    assert metadata["operator"] is None
    assert metadata["owner"] is None
    assert "metadata only" in metadata["water_guardrail"]


def test_google_enrichment_reuses_exact_keys_and_replaces_v1() -> None:
    document = _documents()[tranche.GOOGLE_SOURCE_FILENAME]
    assert document["campus"]["stable_key"] == tranche.GOOGLE_CAMPUS_KEY
    assert document["project"]["stable_key"] == tranche.GOOGLE_PROJECT_KEY
    expected_address = (
        "2100 Bermuda Hundred Road, Chesterfield County, Virginia, United States"
    )
    assert document["campus"]["address"] == expected_address
    assert document["project"]["address"] == expected_address
    assert document["campus"]["roles"] == {"developer": ["Google"]}
    assert document["project"]["roles"] == {"developer": ["Google"]}
    assert len(document["evidence"]) == 3
    assert len(document["lifecycle"]) == 2
    assert document["lifecycle"][-1] == {
        "entity": "project",
        "value": "under_construction",
        "evidence_key": tranche.COUNTY_EVIDENCE_KEY,
        "as_of_date": "2026-07-24",
        "method": "authoritative_physical_status_update",
        "confidence": 0.99,
    }
    county = next(
        row
        for row in document["evidence"]
        if row["key"] == tranche.COUNTY_EVIDENCE_KEY
    )
    metadata = county["metadata"]["google_bermuda_hundred"]
    assert metadata == {
        "county_project_label": "Peanut LLC",
        "address": "2100 Bermuda Hundred Road",
        "status": "Under construction; three buildings",
        "maximum_water_usage_mgd": 6.0,
    }
    witness = tranche._v97_witness()
    assert witness["planned_stable_key_collisions"] == [
        tranche.GOOGLE_CAMPUS_KEY,
        tranche.GOOGLE_PROJECT_KEY,
    ]
    assert witness["prospective_google_integration_mode"] == (
        "replace_v1_source_never_co_select"
    )
    assert witness["google_v1_selected"] is True


def test_digital_drive_is_one_two_building_group_at_county_address() -> None:
    document = _documents()[tranche.DIGITAL_DRIVE_SOURCE_FILENAME]
    assert (
        document["campus"]["stable_key"] == tranche.DIGITAL_DRIVE_CAMPUS_KEY
    )
    assert (
        document["project"]["stable_key"] == tranche.DIGITAL_DRIVE_PROJECT_KEY
    )
    assert document["project"]["address"].startswith("1551 Digital Drive")
    assert document["lifecycle"] == [
        {
            "entity": "project",
            "value": "under_construction",
            "evidence_key": tranche.COUNTY_EVIDENCE_KEY,
            "as_of_date": "2026-07-24",
            "method": "authoritative_physical_status_update",
            "confidence": 0.99,
        }
    ]
    assert document["capacities"] == []
    county = next(
        row
        for row in document["evidence"]
        if row["key"] == tranche.COUNTY_EVIDENCE_KEY
    )
    assert county["metadata"]["chirisa_digital_drive"] == {
        "address": "1551 Digital Drive",
        "status": "Under construction; two buildings",
        "maximum_water_usage": "None anticipated; closed system",
    }
    powerhouse = next(
        row
        for row in document["evidence"]
        if row["key"] == tranche.POWERHOUSE_DIGITAL_EVIDENCE_KEY
    )
    guardrail = powerhouse["metadata"]["address_reconciliation_guardrail"]
    assert "1600" in guardrail
    assert "1551" in guardrail
    assert "creates no address alias" in guardrail


def test_ctp02_ctp03_is_grouped_and_ctp04_is_not_assigned() -> None:
    document = _documents()[tranche.CTP_SOURCE_FILENAME]
    assert document["campus"]["stable_key"] == tranche.CTP_CAMPUS_KEY
    assert document["project"]["stable_key"] == tranche.CTP_PROJECT_KEY
    assert document["project"]["address"].startswith(
        "1381 Meadowville Tech Parkway"
    )
    assert document["lifecycle"] == [
        {
            "entity": "project",
            "value": "under_construction",
            "evidence_key": tranche.CHIRISA_EVIDENCE_KEY,
            "as_of_date": "2026-07-24",
            "method": "authoritative_physical_status_update",
            "confidence": 0.98,
        }
    ]
    assert document["capacities"] == []
    chirisa = next(
        row
        for row in document["evidence"]
        if row["key"] == tranche.CHIRISA_EVIDENCE_KEY
    )
    assert chirisa["metadata"]["ctp02_ctp03"]["status_wording"] == (
        "CTP-02 & CTP-03 – in construction"
    )
    assert chirisa["metadata"]["ctp04_ctp05_ctp06"]["status_wording"] == (
        "reserved for future use"
    )
    assert "one grouped project" in chirisa["metadata"]["phase_guardrail"]
    serialized = json.dumps(document, sort_keys=True)
    assert "curated:chirisa-ctp04" not in serialized
    assert "critical_it_mw" not in serialized
    assert "grid_connection_mw" not in serialized


def test_review_ledger_has_four_sources_and_three_nonpromotions() -> None:
    ledger = tranche._review_ledger(RECORDED_AT)
    assert ledger["candidate_count"] == 7
    assert ledger["governed_source_candidate_count"] == 4
    assert ledger["review_only_count"] == 3
    assert ledger["published"] is False
    by_id = {row["candidate_id"]: row for row in ledger["candidates"]}
    assert by_id["chirisa-ctp04"]["decision"] == (
        "review_only_future_use_and_county_phase_conflict"
    )
    hcl = by_id["hcltech-bhubaneswar-ai-data-center"]
    assert hcl["decision"] == "review_only_proposal_and_mou"
    assert hcl["stable_key_created"] is False
    assert hcl["lifecycle_claim_created"] is False
    assert hcl["reported_wording"] == "plans to set-up"
    hut8 = by_id["hut8-beacon-point-phase2"]
    assert hut8["reported_second_lease_critical_it_mw"] == 352
    assert hut8["site_preparation_assigned_to_phase2"] is False
    assert hut8["stable_key_created"] is False
    assert hut8["lifecycle_claim_created"] is False


def test_epoch_chester_is_exactly_witnessed_and_never_merged() -> None:
    witness = tranche._v97_witness()
    epoch = witness["existing_epoch_chester_record"]
    assert epoch["stable_key"] == tranche.EPOCH_CHESTER_STABLE_KEY
    assert epoch["name"] == "CoreWeave Chester VA"
    assert epoch["address"] == tranche.EPOCH_CHESTER_ADDRESS
    assert epoch["merge_with_ctp_or_digital_drive_asserted"] is False
    ledger = tranche._review_ledger(RECORDED_AT)
    reconciliation = ledger["cross_record_reconciliation"][
        "epoch_coreweave_chester"
    ]
    assert reconciliation["merged_with_1381_meadowville_group"] is False
    assert reconciliation["merged_with_1551_digital_drive_group"] is False


def test_capture_bundle_is_exact_frozen_private_and_retains_404() -> None:
    capture = tranche.resolve_external_capture(tranche.CAPTURE_ORIGIN)
    tranche._validate_capture_directory()
    assert len(tranche.CAPTURES) == 9
    assert len(tranche.CAPTURE_FILE_PINS) == tranche.CAPTURE_FILE_COUNT == 20
    assert sum(
        size for size, _digest in tranche.CAPTURE_FILE_PINS.values()
    ) == tranche.CAPTURE_TOTAL_BYTES
    assert tranche.tree_digest(capture) == (
        tranche.CAPTURE_TREE_SHA256
    )
    assert stat.S_IMODE(capture.stat().st_mode) == 0o555
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o444
        for path in capture.iterdir()
    )
    inventory = tranche._retrieval_inventory(RECORDED_AT)
    assert inventory["successful_http_200_body_captures"] == 9
    assert inventory["retained_rejected_http_captures"] == 1
    rejected = inventory["retained_rejected_capture"]
    assert rejected["http_status"] == 404
    assert rejected["decision"] == "retained_rejected_wrong_route_capture"
    assert rejected["normalized_claim_use"] is False
    assert inventory["raw_capture_redistributed"] is False


def test_chesterfield_pdf_is_hash_bound_but_creates_no_spatial_claim() -> None:
    county = tranche._county_evidence()
    pdf = county["metadata"]["map_pdf_private_capture"]
    assert pdf["bytes"] == 2_815_406
    assert pdf["sha256"] == tranche.CAPTURE_FILE_PINS[
        "chesterfield_map.body"
    ][1]
    assert pdf["headers_sha256"] == tranche.CAPTURE_FILE_PINS[
        "chesterfield_map.headers"
    ][1]
    assert pdf["normalized_claim_use"] is False
    assert pdf["coordinate_or_geometry_claim_created"] is False


def test_v97_is_pinned_and_only_google_keys_are_expected_collisions() -> None:
    witness = tranche._v97_witness()
    assert witness["release_id"] == "2026-07-22-open-seed-v97"
    assert witness["recorded_at"] == "2026-07-22T06:06:40Z"
    assert witness["curated_input_count"] == 519
    assert witness["entity_count"] == 1_053
    assert witness["evidence_count"] == 693
    assert witness["release_tree_sha256"] == tranche.V97_RELEASE_TREE_SHA256
    assert witness["planned_stable_key_collisions"] == [
        tranche.GOOGLE_CAMPUS_KEY,
        tranche.GOOGLE_PROJECT_KEY,
    ]
    assert len(witness["planned_new_stable_keys"]) == 6


def test_builder_has_no_publisher_and_builds_private_stages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_private_stages(tmp_path, monkeypatch)
    assert not hasattr(tranche, "publish")
    assert not hasattr(tranche, "_publish")
    source = inspect.getsource(tranche.prepare_candidate)
    assert "_promote" not in source
    assert ".rename(" not in source
    assert not tranche.PROSPECTIVE_ARTIFACT.exists()

    prepared = tranche.prepare_candidate(recorded_at=RECORDED_AT)
    try:
        result = tranche.candidate_result(prepared)
        assert result["status"] == (
            "PREPUBLICATION_CANDIDATE_BUILT_NOT_PUBLISHED"
        )
        assert result["curated_source_candidates"] == 4
        assert result["review_only_candidates"] == 3
        assert result["offline_import_counts"] == {
            "entities": 8,
            "entity_snapshots": 8,
            "evidence": 7,
            "lifecycle_observations": 5,
            "operating_model_observations": 0,
            "workload_observations": 1,
            "capacity_estimates": 1,
        }
        assert result["published"] is False
        assert result["prospective_final_artifact_exists"] is False
        assert not any(result["prospective_final_sources_exist"].values())
        assert result["release_integration"] == "none"
        assert result["federation_integration"] == "none"
        assert result["identity_integration"] == "none"
        assert result["construction_master_integration"] == "none"
        assert result["map_integration"] == "none"
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


def test_two_fixed_prepublication_replays_are_byte_identical(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_private_stages(tmp_path, monkeypatch)
    first = tranche.prepare_candidate(recorded_at=RECORDED_AT)
    second = tranche.prepare_candidate(recorded_at=RECORDED_AT)
    try:
        assert first.source_stage != second.source_stage
        assert first.artifact_stage != second.artifact_stage
        assert tranche.tree_digest(first.source_stage) == tranche.tree_digest(
            second.source_stage
        )
        assert tranche.tree_digest(first.artifact_stage) == tranche.tree_digest(
            second.artifact_stage
        )
        for name in tranche.SOURCE_FILENAMES:
            assert (first.source_stage / name).read_bytes() == (
                second.source_stage / name
            ).read_bytes()
        for name in tranche.CLOSED_FILES:
            assert (first.artifact_stage / name).read_bytes() == (
                second.artifact_stage / name
            ).read_bytes()
    finally:
        _cleanup(first)
        _cleanup(second)


def test_candidate_build_is_network_independent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_private_stages(tmp_path, monkeypatch)

    def blocked(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network access is forbidden during replay")

    monkeypatch.setattr(socket, "create_connection", blocked)
    prepared = tranche.prepare_candidate(recorded_at=RECORDED_AT)
    try:
        assert tranche.validate_candidate(
            prepared.artifact_stage,
            prepared.source_stage,
        )["published"] is False
    finally:
        _cleanup(prepared)


def test_artifact_is_compact_facts_and_hashes_not_raw_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_private_stages(tmp_path, monkeypatch)
    prepared = tranche.prepare_candidate(recorded_at=RECORDED_AT)
    try:
        entries = {path.name for path in prepared.artifact_stage.iterdir()}
        assert entries == tranche.CLOSED_FILES
        assert not any(
            name.endswith((".body", ".headers", ".pdf")) for name in entries
        )
        rights = json.loads(
            (prepared.artifact_stage / "rights-and-disposition.json").read_text(
                encoding="utf-8"
            )
        )
        assert rights["artifact_is_hash_and_factual_extract_only"] is True
        assert rights["raw_capture_redistributed"] is False
        assert rights["raw_response_bodies_retained_in_artifact"] is False
        assert rights["raw_response_headers_retained_in_artifact"] is False
        assert rights["publisher_media_retained_in_artifact"] is False
    finally:
        _cleanup(prepared)


def test_mutated_capture_copy_fails_closed(tmp_path: Path) -> None:
    copied = tmp_path / "capture"
    shutil.copytree(tranche.resolve_external_capture(tranche.CAPTURE_ORIGIN), copied)
    for path in copied.iterdir():
        path.chmod(0o444)
    copied.chmod(0o555)
    tranche._validate_capture_directory(copied)

    copied.chmod(0o755)
    body = copied / "humboldt.body"
    body.chmod(0o644)
    body.write_bytes(body.read_bytes() + b"\n")
    body.chmod(0o444)
    copied.chmod(0o555)
    with pytest.raises(RuntimeError, match="pinned file differs"):
        tranche._validate_capture_directory(copied)
    tranche._validate_capture_directory()
