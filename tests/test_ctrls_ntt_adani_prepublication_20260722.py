from __future__ import annotations

import inspect
import json
from pathlib import Path
import shutil
import socket
import stat

import pytest

try:
    from datacenter_atlas.datacenter_atlas import (
        ctrls_ntt_adani_prepublication_20260722 as tranche,
    )
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import (  # type: ignore[no-redef]
        ctrls_ntt_adani_prepublication_20260722 as tranche,
    )


RECORDED_AT = "2026-07-22T05:00:00Z"


def _documents() -> dict[str, dict[str, object]]:
    return tranche.expected_source_documents()


def _cleanup(prepared: tranche.PreparedCandidate) -> None:
    if prepared.source_stage.exists():
        shutil.rmtree(prepared.source_stage)
    if prepared.artifact_stage.exists():
        shutil.rmtree(prepared.artifact_stage)


def _configure_private_stages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    sources = tmp_path / "sources"
    artifacts = tmp_path / "source_artifacts"
    sources.mkdir()
    artifacts.mkdir()
    monkeypatch.setattr(tranche, "SOURCES_ROOT", sources)
    monkeypatch.setattr(tranche, "ARTIFACT_ROOT", artifacts)
    monkeypatch.setattr(tranche, "PROSPECTIVE_ARTIFACT", artifacts / "candidate")
    return sources, artifacts


def test_exact_two_source_inventory_and_sparse_normalized_output() -> None:
    documents = _documents()
    assert tuple(documents) == tranche.SOURCE_FILENAMES
    assert tuple(documents) == (
        tranche.CHANDANVELLY_SOURCE_FILENAME,
        tranche.PHARMACITY_SOURCE_FILENAME,
    )
    assert sum(len(document["evidence"]) for document in documents.values()) == 3
    assert sum(len(document["lifecycle"]) for document in documents.values()) == 2
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
        for entity_name in ("campus", "project"):
            entity = document[entity_name]
            assert entity["roles"] == {"developer": ["CtrlS Datacenters Ltd"]}
            assert entity["coordinates"] is None
            assert entity["geometry"] is None


def test_current_dated_page_directly_binds_both_named_builds() -> None:
    documents = _documents()
    expected = {
        tranche.CHANDANVELLY_SOURCE_FILENAME: (
            tranche.CHANDANVELLY_CAMPUS_KEY,
            tranche.CHANDANVELLY_PROJECT_KEY,
            tranche.CHANDANVELLY_STATUS_EVIDENCE_KEY,
            0.99,
        ),
        tranche.PHARMACITY_SOURCE_FILENAME: (
            tranche.PHARMACITY_CAMPUS_KEY,
            tranche.PHARMACITY_PROJECT_KEY,
            tranche.PHARMACITY_STATUS_EVIDENCE_KEY,
            0.98,
        ),
    }
    for name, (campus_key, project_key, evidence_key, confidence) in expected.items():
        document = documents[name]
        assert document["campus"]["stable_key"] == campus_key
        assert document["project"]["stable_key"] == project_key
        assert document["lifecycle"] == [
            {
                "entity": "project",
                "value": "under_construction",
                "evidence_key": evidence_key,
                "as_of_date": "2026-07-21",
                "method": "authoritative_physical_status_update",
                "confidence": confidence,
            }
        ]
        evidence = next(
            row for row in document["evidence"] if row["key"] == evidence_key
        )
        assert evidence["source_url"] == "https://www.ctrls.com/datacenter-hyderabad/"
        assert evidence["published_at"] is None
        assert evidence["retrieved_at"] == tranche.CAPTURE_RETRIEVED_AT
        assert evidence["content_hash"] == (
            "1822fb3465dd181fd8329f6d8b043a6e4c2bdf8eb1ba6e92633398095f0290fe"
        )
        metadata = evidence["metadata"]
        assert metadata["page_date_modified_as_reported"] == (
            "2026-07-21T12:24:34+05:30"
        )
        assert metadata["status_wording_as_reported"] == (
            "We’re building two of India’s largest AI-ready datacenter campuses."
        )
        assert metadata["normalized_lifecycle"] == "under_construction"
        assert metadata["content_hash_verification"] == "fetched_bytes_sha256"
        assert metadata["private_capture"]["retained_private"] is True
        assert metadata["private_capture"]["redistributed"] is False


def test_capacity_energy_efficiency_and_classification_guardrails() -> None:
    documents = _documents()
    chandan = documents[tranche.CHANDANVELLY_SOURCE_FILENAME]
    current = next(
        row
        for row in chandan["evidence"]
        if row["key"] == tranche.CHANDANVELLY_STATUS_EVIDENCE_KEY
    )
    assert current["metadata"]["current_page_capacity_not_normalized"] == {
        "wording": "Over 700 MW Capacity Scalable to 1.4GW",
        "reason": (
            "The current page does not type the displayed capacity as IT, gross "
            "facility, grid connection, generation, or current draw."
        ),
        "capacity_row_created": False,
    }
    assert current["metadata"]["sanctioned_power_not_normalized"][
        "capacity_row_created"
    ] is False
    announcement = next(
        row
        for row in chandan["evidence"]
        if row["key"] == tranche.CHANDANVELLY_ANNOUNCEMENT_EVIDENCE_KEY
    )
    assert announcement["metadata"]["announcement_only"] is True
    assert announcement["metadata"]["lifecycle_claim_from_this_evidence"] is False
    assert announcement["metadata"]["reported_potential_it_load"][
        "wording"
    ] == "over 600 MW IT load when fully developed"
    assert announcement["metadata"]["reported_potential_it_load"][
        "capacity_row_created"
    ] is False
    assert announcement["metadata"]["reported_phase_1_sanctioned_power"][
        "capacity_row_created"
    ] is False
    assert announcement["metadata"]["design_pue_not_normalized"][
        "efficiency_row_created"
    ] is False

    pharmacity = documents[tranche.PHARMACITY_SOURCE_FILENAME]
    metadata = pharmacity["evidence"][0]["metadata"]
    assert metadata["capacity_not_normalized"]["wording"] == (
        "Up to 750 MW Capacity Scalable to 1.2GW"
    )
    assert metadata["capacity_not_normalized"]["capacity_row_created"] is False
    assert metadata["green_power_not_normalized"]["wording"] == (
        "100% Green Power Project"
    )
    assert metadata["green_power_not_normalized"][
        "energy_or_efficiency_row_created"
    ] is False
    for document in documents.values():
        assert document["capacities"] == []
        assert document["workloads"] == []
        assert document["operating_models"] == []


def test_twelve_assessments_accept_two_and_reject_ten_without_records() -> None:
    assessment = tranche._candidate_assessment(RECORDED_AT)
    candidates = assessment["candidates"]
    accepted = [
        row
        for row in candidates
        if row["decision"] == "governed_prepublication_current_physical_build"
    ]
    rejected = [row for row in candidates if row not in accepted]
    assert assessment["candidate_count"] == len(candidates) == 12
    assert assessment["governed_source_candidate_count"] == len(accepted) == 2
    assert assessment["review_only_count"] == len(rejected) == 10
    assert {row["candidate_id"] for row in accepted} == {
        "ctrls-chandanvelly-current-build",
        "ctrls-pharmacity-current-build",
    }
    for row in rejected:
        assert row["source_paths"] == []
        assert row["stable_key_created"] is False
        assert row["lifecycle_claim_created"] is False
        assert "campus_stable_key" not in row
        assert "project_stable_key" not in row

    by_id = {row["candidate_id"]: row for row in rejected}
    assert by_id["ctrls-bhopal-greenfield"]["decision"] == (
        "review_only_virtual_ceremony_without_site_activity"
    )
    assert "four data centers" in by_id["ntt-india-four-unnamed-builds"]["reason"]
    assert by_id["ntt-india-four-unnamed-builds"]["capacity_claim_created"] is False
    assert by_id["ntt-bengaluru-4b-4c"]["decision"] == (
        "review_only_planned_capacity_without_physical_status"
    )
    assert by_id["ntt-noida-2-building-b"]["decision"] == (
        "review_only_future_capacity_without_current_status"
    )
    assert by_id["adaniconnex-hyderabad-future-phases"]["decision"] == (
        "review_only_no_distinct_physical_successor"
    )
    assert by_id["adaniconnex-noida-future-phases"]["decision"] == (
        "review_only_no_distinct_physical_successor"
    )
    assert assessment["out_of_scope_already_in_v95"] == [
        "AdaniConneX Navi Mumbai Current Phased Development",
        "AdaniConneX Pune PNQ04 Current Build",
    ]


def test_capture_bundle_is_exact_frozen_private_and_complete() -> None:
    capture = tranche.resolve_external_capture(tranche.CAPTURE_ORIGIN)
    tranche._validate_capture_directory()
    assert len(tranche.CAPTURES) == 15
    assert len(tranche.CAPTURE_FILE_PINS) == tranche.CAPTURE_FILE_COUNT == 30
    assert tranche.CAPTURE_TOTAL_BYTES == 3_431_628
    assert (
        sum(size for size, _digest in tranche.CAPTURE_FILE_PINS.values())
        == tranche.CAPTURE_TOTAL_BYTES
    )
    assert tranche.tree_digest(capture) == (
        tranche.CAPTURE_TREE_SHA256
    )
    assert tranche.CAPTURE_TREE_SHA256 == (
        "702b3c5257c81b60d2d5b16df0cf9c41df826012018bbe72d5f79942255bbecc"
    )
    assert stat.S_IMODE(capture.stat().st_mode) == 0o555
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o444
        for path in capture.iterdir()
    )
    inventory = tranche._retrieval_inventory(RECORDED_AT)
    assert inventory["successful_http_200_body_captures"] == 15
    assert inventory["raw_capture_redistributed"] is False
    assert len(inventory["complete_private_file_inventory"]) == 30


def test_v95_and_current_source_collision_witnesses_are_empty() -> None:
    witness = tranche._v95_witness()
    assert witness["release_id"] == "2026-07-22-open-seed-v95"
    assert witness["recorded_at"] == "2026-07-22T04:21:58Z"
    assert witness["selected_input_count"] == 507
    assert witness["entity_count"] == 1_029
    assert witness["public_evidence_count"] == 678
    assert witness["planned_stable_key_collisions"] == []
    assert witness["planned_evidence_key_collisions"] == []
    assert witness["planned_selected_path_collisions"] == []
    assert witness["pins"]["definition_sha256"] == tranche.V95_DEFINITION_PIN[1]

    current = tranche._current_source_collision_witness()
    assert current["planned_source_filename_collisions"] == []
    assert current["planned_stable_key_collisions"] == []
    assert current["planned_evidence_key_collisions"] == []
    assert current["planned_identity_collisions"] == []


def test_accepted_later_identity_collision_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tranche, "SOURCES_ROOT", tmp_path)
    collision = {
        "campus": {
            "stable_key": "curated:unrelated-key",
            "name": "Existing CtrlS Pharmacity campus",
            "address": "Hyderabad, India",
        },
        "project": {},
        "evidence": [],
    }
    (tmp_path / "curated-official-later-source.json").write_text(
        json.dumps(collision), encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="collide with a source added after v95"):
        tranche._current_source_collision_witness()


def test_builder_is_offline_private_replayable_and_has_no_publisher(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, artifacts = _configure_private_stages(tmp_path, monkeypatch)

    def no_network(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("network access attempted during offline build")

    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket, "getaddrinfo", no_network)
    assert not hasattr(tranche, "publish")
    assert not hasattr(tranche, "_publish")
    source = inspect.getsource(tranche.prepare_candidate)
    assert "_promote" not in source
    assert ".rename(" not in source
    assert "source_stage.replace(" not in source
    assert "artifact_stage.replace(" not in source
    assert not tranche.PROSPECTIVE_ARTIFACT.exists()
    assert not any((sources / name).exists() for name in tranche.SOURCE_FILENAMES)

    prepared = tranche.prepare_candidate(
        recorded_at=RECORDED_AT,
        source_parent=sources,
        artifact_parent=artifacts,
    )
    try:
        manifest = tranche.validate_candidate(
            prepared.artifact_stage, prepared.source_stage
        )
        assert manifest["published"] is False
        assert manifest["publisher_function_present"] is False
        assert manifest["curated_source_candidates"] == 2
        assert manifest["review_only_candidates"] == 10
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
        assert {path.name for path in prepared.artifact_stage.iterdir()} == (
            tranche.CLOSED_FILES
        )
        snapshot = json.loads(
            (prepared.artifact_stage / "source-snapshot.json").read_text()
        )
        assert snapshot["totals"] == {
            "candidate_assessments": 12,
            "source_records": 2,
            "governed_prepublication_candidates": 2,
            "review_only_candidates": 10,
            "distinct_campuses_in_source_records": 2,
            "projects": 2,
            "distinct_entity_snapshots": 4,
            "new_entities_against_v95": 4,
            "evidence_records": 3,
            "lifecycle_observations": 2,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 0,
            "energy_consumption_observations": 0,
            "facility_type_observations": 0,
            "coordinate_observations": 0,
            "geometry_observations": 0,
            "satellite_observations": 0,
        }
        assert snapshot["integration"]["published"] is False
        assert snapshot["integration"]["release_integration"] == "none"
    finally:
        _cleanup(prepared)


def test_source_artifact_and_final_path_tamper_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, artifacts = _configure_private_stages(tmp_path, monkeypatch)
    prepared = tranche.prepare_candidate(
        recorded_at=RECORDED_AT,
        source_parent=sources,
        artifact_parent=artifacts,
    )
    try:
        source = prepared.source_stage / tranche.CHANDANVELLY_SOURCE_FILENAME
        source.write_bytes(source.read_bytes() + b"\n")
        with pytest.raises(RuntimeError, match="staged source differs"):
            tranche.validate_candidate(prepared.artifact_stage, prepared.source_stage)
        source.write_bytes(
            tranche._canonical(
                tranche.expected_source_documents()[
                    tranche.CHANDANVELLY_SOURCE_FILENAME
                ]
            )
        )
        assessment = prepared.artifact_stage / "candidate-assessment.json"
        assessment.write_bytes(assessment.read_bytes() + b" ")
        with pytest.raises(RuntimeError, match="candidate manifest pin differs"):
            tranche.validate_candidate(prepared.artifact_stage, prepared.source_stage)
    finally:
        _cleanup(prepared)

    (sources / tranche.CHANDANVELLY_SOURCE_FILENAME).write_text(
        "collision", encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="prospective final-path collision"):
        tranche.prepare_candidate(
            recorded_at=RECORDED_AT,
            source_parent=sources,
            artifact_parent=artifacts,
        )
