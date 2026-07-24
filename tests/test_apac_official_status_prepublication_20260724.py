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
        apac_official_status_prepublication_20260724 as tranche,
    )
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import (  # type: ignore[no-redef]
        apac_official_status_prepublication_20260724 as tranche,
    )


RECORDED_AT = "2026-07-24T22:20:00Z"


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


def _documents() -> dict[str, dict[str, object]]:
    return tranche.expected_source_documents()


def test_exact_three_sparse_source_documents() -> None:
    documents = _documents()
    assert tuple(documents) == tranche.SOURCE_FILENAMES
    assert len(documents) == 3
    for document in documents.values():
        assert document["schema_version"] == "1.1"
        assert len(document["evidence"]) == 1
        assert len(document["lifecycle"]) == 1
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


def test_only_supported_lifecycle_observations_are_normalized() -> None:
    documents = _documents()
    expected = {
        tranche.CONVERGE_SOURCE_FILENAME: (
            tranche.CONVERGE_CAMPUS_KEY,
            tranche.CONVERGE_PROJECT_KEY,
            "operational",
            "Angeles City, Pampanga, Philippines",
        ),
        tranche.GSA02_SOURCE_FILENAME: (
            tranche.GSA02_CAMPUS_KEY,
            tranche.GSA02_PROJECT_KEY,
            "under_construction",
            "Eastern Economic Corridor, Chonburi Province, Thailand",
        ),
        tranche.GEDC01_SOURCE_FILENAME: (
            tranche.GEDC01_CAMPUS_KEY,
            tranche.GEDC01_PROJECT_KEY,
            "under_construction",
            "Eastern Economic Corridor, Rayong Province, Thailand",
        ),
    }
    for name, (
        campus_key,
        project_key,
        lifecycle,
        address,
    ) in expected.items():
        document = documents[name]
        assert document["campus"]["stable_key"] == campus_key
        assert document["project"]["stable_key"] == project_key
        assert document["lifecycle"] == [
            {
                "entity": "project",
                "value": lifecycle,
                "evidence_key": document["evidence"][0]["key"],
                "as_of_date": "2026-07-24",
                "method": "authoritative_physical_status_update",
                "confidence": 0.99,
            }
        ]
        for entity_name in ("campus", "project"):
            entity = document[entity_name]
            assert entity["address"] == address
            assert entity["roles"] == {}
            assert entity["coordinates"] is None
            assert entity["geometry"] is None


def test_statuses_are_last_observed_and_current_afterward_is_unknown() -> None:
    for document in _documents().values():
        evidence = document["evidence"][0]
        assert evidence["published_at"] == "2026-07-24"
        metadata = evidence["metadata"]
        assert metadata["status_semantics"] == (
            "dated_last_observed_status_current_status_after_observation_unknown"
        )
        guardrail = metadata["normalization_guardrail"]
        assert "No coordinate" in guardrail
        assert "capacity" in guardrail
        assert "computer-vision claim" in guardrail


def test_gulf_documents_preserve_codes_and_share_only_source_bytes() -> None:
    documents = _documents()
    gsa = documents[tranche.GSA02_SOURCE_FILENAME]
    gedc = documents[tranche.GEDC01_SOURCE_FILENAME]
    assert gsa["evidence"][0]["key"] == tranche.GSA02_EVIDENCE_KEY
    assert gedc["evidence"][0]["key"] == tranche.GEDC01_EVIDENCE_KEY
    assert gsa["evidence"][0]["content_hash"] == (
        gedc["evidence"][0]["content_hash"]
    )
    assert gsa["evidence"][0]["metadata"]["reported_project_code"] == "GSA02"
    assert gedc["evidence"][0]["metadata"]["reported_project_code"] == "GEDC01"
    for document in (gsa, gedc):
        metadata = document["evidence"][0]["metadata"]
        assert metadata["reported_status_wording"] == (
            "currently under construction"
        )
        assert metadata["capacity_rows_created"] is False
        assert metadata["commercial_operation_schedule_rows_created"] is False
        assert (
            metadata["other_filing_projects_normalized_in_this_source"]
            is False
        )


def test_discovery_ledger_has_twelve_bounded_decisions() -> None:
    ledger = tranche._discovery_ledger(RECORDED_AT)
    assert ledger["candidate_count"] == 12
    assert ledger["governed_source_candidate_count"] == 3
    assert ledger["review_only_count"] == 7
    assert ledger["already_governed_count"] == 1
    assert ledger["exact_v97_match_count"] == 1
    assert ledger["published"] is False
    assert ledger["research_window"] == {
        "published_on_or_after": "2026-07-23",
        "published_on_or_before": "2026-07-24",
    }
    assert all(row["source_urls"] for row in ledger["candidates"])
    assert all(
        row["published_at"] in {"2026-07-23", "2026-07-24"}
        for row in ledger["candidates"]
    )


def test_ledger_keeps_non_physical_and_duplicate_findings_out() -> None:
    by_id = {
        row["candidate_id"]: row
        for row in tranche._discovery_ledger(RECORDED_AT)["candidates"]
    }
    assert by_id["gulf-gedc03-gedc04"]["decision"] == (
        "review_only_incorporation_and_future_preparation"
    )
    assert by_id["hcltech-bhubaneswar-ai-data-center"]["decision"] == (
        "review_only_proposal_and_mou"
    )
    assert by_id["polar-dra02-drangedal"]["decision"] == (
        "review_only_announced_future_facility"
    )
    assert by_id["datagrid-north-makarewa-southland"]["decision"] == (
        "review_only_financing_and_future_start_language"
    )
    assert by_id[
        "anonymous-klang-valley-data-center-grid-works"
    ]["decision"] == (
        "review_only_power_infrastructure_and_unknown_identity"
    )
    assert by_id[
        "blackpool-silicon-sands-first-data-center"
    ]["decision"] == "review_only_procurement_and_approval"
    assert by_id["aws-bharat-future-city"]["decision"] == (
        "exact_v97_match_no_new_entity"
    )
    assert by_id[
        "humboldt-tennessee-unnamed-data-center"
    ]["decision"].startswith("already_governed_in_separate")


def test_v97_has_no_planned_key_evidence_or_url_collision() -> None:
    witness = tranche._v97_witness()
    assert witness["release_id"] == "2026-07-22-open-seed-v97"
    assert witness["recorded_at"] == "2026-07-22T06:06:40Z"
    assert witness["curated_input_count"] == 519
    assert witness["entity_count"] == 1_053
    assert witness["evidence_count"] == 693
    assert witness["planned_stable_key_collisions"] == []
    assert witness["planned_evidence_key_collisions"] == []
    assert witness["planned_source_url_collisions"] == []
    assert len(witness["planned_new_stable_keys"]) == 6
    assert witness["converge_semantic_matches"] == []
    assert witness["gulf_project_code_matches"] == []
    assert witness["rayong_thailand_rows"] == []


def test_chonburi_nearby_projects_are_explicit_non_merges() -> None:
    nearby = tranche._v97_witness()[
        "chonburi_semantic_nearby_rejected"
    ]
    assert {row["stable_key"] for row in nearby} == {
        tranche.DAYONE_CAMPUS_KEY,
        tranche.DAYONE_PROJECT_KEY,
        tranche.DIGITAL_EDGE_CAMPUS_KEY,
        tranche.DIGITAL_EDGE_PROJECT_KEY,
    }
    assert all(
        row["merge_decision"]
        == "reject_merge_different_named_operator_project"
        for row in nearby
    )
    assert tranche.GSA02_CAMPUS_KEY not in {
        row["stable_key"] for row in nearby
    }


def test_capture_bundle_is_exact_frozen_and_primary_only() -> None:
    tranche._validate_capture_directory()
    assert len(tranche.CAPTURE_FILE_PINS) == tranche.CAPTURE_FILE_COUNT == 8
    assert sum(
        size for size, _digest in tranche.CAPTURE_FILE_PINS.values()
    ) == tranche.CAPTURE_TOTAL_BYTES
    assert tranche.tree_digest(tranche.CAPTURE_ORIGIN) == (
        tranche.CAPTURE_TREE_SHA256
    )
    assert stat.S_IMODE(tranche.CAPTURE_ORIGIN.stat().st_mode) == 0o555
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o444
        for path in tranche.CAPTURE_ORIGIN.iterdir()
    )
    converge = (tranche.CAPTURE_ORIGIN / "converge.body").read_bytes()
    assert b"Friday, July 24th 2026" in converge
    assert b"Angeles Data Center serving as a strategic hub" in converge
    viewer = (tranche.CAPTURE_ORIGIN / "gulf-viewer.body").read_bytes()
    assert tranche.GULF_WRAPPER_URL.encode() in viewer
    wrapper = (tranche.CAPTURE_ORIGIN / "gulf-wrapper.body").read_bytes()
    assert tranche.GULF_PDF_URL.encode().replace(b"&", b"&amp;")[:120] in (
        wrapper.replace(b"&amp;", b"&")
    )
    assert (tranche.CAPTURE_ORIGIN / "gulf-filing.body").read_bytes().startswith(
        b"%PDF"
    )


def test_retrieval_inventory_records_complete_delivery_chain() -> None:
    inventory = tranche._retrieval_inventory(RECORDED_AT)
    assert inventory["successful_http_200_body_captures"] == 4
    assert inventory["raw_capture_redistributed"] is False
    assert inventory["private_capture_directory_frozen"] is True
    by_id = {
        row["capture_id"]: row for row in inventory["controlled_captures"]
    }
    assert by_id["converge-angeles-newsroom"]["claim_use"] == (
        "normalized_operational_observation"
    )
    assert by_id["gulf-official-viewer"]["claim_use"] == (
        "official_viewer_and_canonical_url_witness"
    )
    assert by_id["gulf-document-wrapper"]["claim_use"] == (
        "document_delivery_chain_witness"
    )
    assert by_id["gulf-official-filing-pdf"]["claim_use"] == (
        "normalized_gsa02_gedc01_and_review_context"
    )


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
        assert result["candidate_assessments"] == 12
        assert result["curated_source_candidates"] == 3
        assert result["review_only_candidates"] == 7
        assert result["already_governed_candidates"] == 1
        assert result["exact_v97_match_candidates"] == 1
        assert result["offline_import_counts"] == {
            "entities": 6,
            "entity_snapshots": 6,
            "evidence": 3,
            "lifecycle_observations": 3,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 0,
        }
        compatibility = result["v97_compatibility_import"]
        assert compatibility["counts"] == {
            "entities": 10,
            "entity_snapshots": 10,
            "evidence": 6,
            "lifecycle_observations": 5,
            "operating_model_observations": 1,
            "workload_observations": 0,
            "capacity_estimates": 0,
        }
        assert compatibility["planned_entity_rows"] == 6
        assert compatibility["nearby_preserved_entity_rows"] == 4
        assert compatibility["merged_entity_rows"] == 0
        assert result["planned_stable_key_collisions"] == []
        assert result["published"] is False
        assert result["prospective_final_artifact_exists"] is False
        assert not any(result["prospective_final_sources_exist"].values())
        assert result["release_integration"] == "none"
        assert result["federation_integration"] == "none"
        assert result["identity_integration"] == "none"
        assert result["construction_master_integration"] == "none"
        assert result["map_integration"] == "none"
        assert result["ledger_integration"] == "none"
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
            RECORDED_AT,
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
            name.endswith((".body", ".headers", ".html", ".pdf"))
            for name in entries
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
    shutil.copytree(tranche.CAPTURE_ORIGIN, copied)
    for path in copied.iterdir():
        path.chmod(0o444)
    copied.chmod(0o555)
    tranche._validate_capture_directory(copied)

    copied.chmod(0o755)
    body = copied / "gulf-filing.body"
    body.chmod(0o644)
    body.write_bytes(body.read_bytes() + b"\n")
    body.chmod(0o444)
    copied.chmod(0o555)
    with pytest.raises(RuntimeError, match="pinned file differs"):
        tranche._validate_capture_directory(copied)
    tranche._validate_capture_directory()


def test_source_and_artifact_tampering_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_private_stages(tmp_path, monkeypatch)
    source_candidate = tranche.prepare_candidate(recorded_at=RECORDED_AT)
    artifact_candidate = tranche.prepare_candidate(recorded_at=RECORDED_AT)
    try:
        source = (
            source_candidate.source_stage
            / tranche.CONVERGE_SOURCE_FILENAME
        )
        source.write_bytes(source.read_bytes() + b"\n")
        with pytest.raises(RuntimeError, match="staged source differs"):
            tranche.validate_candidate(
                source_candidate.artifact_stage,
                source_candidate.source_stage,
                RECORDED_AT,
            )

        extra = artifact_candidate.artifact_stage / "unexpected.txt"
        extra.write_text("unexpected", encoding="utf-8")
        extra.chmod(0o600)
        with pytest.raises(RuntimeError, match="closed file set differs"):
            tranche.validate_candidate(
                artifact_candidate.artifact_stage,
                artifact_candidate.source_stage,
                RECORDED_AT,
            )
        extra.unlink()
        readme = artifact_candidate.artifact_stage / "README.md"
        readme.write_bytes(readme.read_bytes() + b"\n")
        with pytest.raises(RuntimeError, match="manifest member pin differs"):
            tranche.validate_candidate(
                artifact_candidate.artifact_stage,
                artifact_candidate.source_stage,
                RECORDED_AT,
            )
    finally:
        _cleanup(source_candidate)
        _cleanup(artifact_candidate)


def test_mutated_v97_definition_pin_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    copied = tmp_path / "v97-definition.json"
    shutil.copy2(tranche.V97_DEFINITION, copied)
    copied.chmod(0o600)
    copied.write_bytes(copied.read_bytes() + b"\n")
    monkeypatch.setattr(tranche, "V97_DEFINITION", copied)
    with pytest.raises(RuntimeError, match="pinned file differs"):
        tranche._v97_witness()


def test_v97_tree_and_prospective_final_paths_remain_unchanged() -> None:
    assert tranche.tree_digest(tranche.V97_RELEASE) == (
        tranche.V97_RELEASE_TREE_SHA256
    )
    assert not tranche.PROSPECTIVE_ARTIFACT.exists()
    assert not any(
        (tranche.SOURCES_ROOT / name).exists()
        for name in tranche.SOURCE_FILENAMES
    )
    witness = tranche._v97_witness()
    assert witness["release_tree_sha256"] == (
        tranche.V97_RELEASE_TREE_SHA256
    )
