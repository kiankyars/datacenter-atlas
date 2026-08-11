from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import shutil
import stat

import pytest

try:
    from datacenter_atlas.datacenter_atlas import (
        hut8_river_bend_official_current_build_gap_20260722 as tranche,
    )
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import (  # type: ignore[no-redef]
        hut8_river_bend_official_current_build_gap_20260722 as tranche,
    )


def _live_source_document() -> dict[str, object]:
    mode = 0o444 if tranche.ARTIFACT.exists() else 0o644
    return tranche._validate_source(tranche.SOURCE, mode=mode)


def test_exact_source_shape_and_schema_correction() -> None:
    document = _live_source_document()
    assert document["schema_version"] == "1.1"
    assert tranche.SOURCE_PIN == (
        16_044,
        "0e5139ef2935accca6e0dafcbde324f5cfb730ff855c526f9b835afe9c7919f4",
    )
    assert document["campus"]["stable_key"] == tranche.CAMPUS_KEY
    assert document["project"]["stable_key"] == tranche.PROJECT_KEY
    assert [row["key"] for row in document["evidence"]] == list(
        tranche.EVIDENCE_KEYS
    )


def test_strict_offline_import_is_idempotent() -> None:
    assert tranche._offline_import(
        tranche.SOURCE, "2026-07-22T03:20:00Z"
    ) == {
        "entities": 2,
        "entity_snapshots": 2,
        "evidence": 3,
        "lifecycle_observations": 1,
        "operating_model_observations": 1,
        "workload_observations": 1,
        "capacity_estimates": 2,
    }


def test_schema_10_cannot_replay_per_evidence_retrieval_times(tmp_path: Path) -> None:
    document = _live_source_document()
    document["schema_version"] = "1.0"
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(document))
    connection, _ = tranche.initialize(tmp_path / "atlas.sqlite")
    with pytest.raises(ValueError, match="retrieved_at must equal"):
        tranche.CuratedOfficialSourceAdapterV11().import_file(
            connection, path, recorded_at="2026-07-22T03:20:00Z"
        )


def test_evidence_cannot_postdate_import(tmp_path: Path) -> None:
    path = tmp_path / "source.json"
    path.write_bytes(tranche.SOURCE.read_bytes())
    connection, _ = tranche.initialize(tmp_path / "atlas.sqlite")
    with pytest.raises(ValueError, match="must not be later"):
        tranche.CuratedOfficialSourceAdapterV11().import_file(
            connection, path, recorded_at="2026-07-22T02:47:01Z"
        )


def test_lifecycle_and_classification_boundaries() -> None:
    document = _live_source_document()
    assert [
        (row["value"], row["as_of_date"], row["method"])
        for row in document["lifecycle"]
    ] == [
        (
            "under_construction",
            "2026-05-06",
            "authoritative_physical_status_update",
        )
    ]
    assert [row["value"] for row in document["operating_models"]] == [
        "hyperscale_lease"
    ]
    assert [row["value"] for row in document["workloads"]] == [
        "ai_specialized_unspecified"
    ]


def test_only_supported_standardized_roles_are_present() -> None:
    document = _live_source_document()
    assert document["campus"]["roles"] == {
        "developer": ["Hut 8"],
        "utility": ["Entergy Louisiana"],
    }
    assert document["project"]["roles"] == {
        "developer": ["Hut 8"],
        "tenant": ["Fluidstack"],
    }
    roles = json.dumps(
        [document["campus"]["roles"], document["project"]["roles"]]
    )
    assert "Google" not in roles
    assert not {"owner", "operator", "user", "customer", "investor"} & {
        key
        for entity in (document["campus"], document["project"])
        for key in entity["roles"]
    }


def test_capacity_dimensions_are_exact_and_nonadditive() -> None:
    capacities = _live_source_document()["capacities"]
    assert [
        (row["entity"], row["metric"], row["stage"], row["base"])
        for row in capacities
    ] == [
        ("project", "critical_it_mw", "contracted", 245),
        ("campus", "grid_connection_mw", "contracted", 330),
    ]
    assert 575 not in [row["base"] for row in capacities]
    assert all(row["target_date"] is None for row in capacities)


@pytest.mark.parametrize(
    "forbidden_metric",
    [
        "gross_facility_mw",
        "annual_energy_mwh",
        "generation_nameplate_mw",
        "pue",
        "wue_l_per_kwh",
    ],
)
def test_forbidden_energy_metric_is_not_normalized(forbidden_metric: str) -> None:
    metrics = {row["metric"] for row in _live_source_document()["capacities"]}
    assert forbidden_metric not in metrics


@pytest.mark.parametrize(
    ("evidence_key", "body_name", "header_name"),
    [
        (
            tranche.LEASE_EVIDENCE,
            "lease-press99-1.htm",
            "lease-press.headers",
        ),
        (tranche.Q1_EVIDENCE, "q1-10q.htm", "q1-10q.headers"),
        (
            tranche.UPDATE_EVIDENCE,
            "update-exhibit99-1.htm",
            "update-exhibit.headers",
        ),
    ],
)
def test_each_evidence_record_has_exact_body_and_header_lineage(
    evidence_key: str, body_name: str, header_name: str
) -> None:
    evidence = {
        row["key"]: row for row in _live_source_document()["evidence"]
    }[evidence_key]
    assert evidence["content_hash"] == tranche.CAPTURE_FILE_PINS[body_name][1]
    assert evidence["metadata"]["capture_headers_sha256"] == (
        tranche.CAPTURE_FILE_PINS[header_name][1]
    )
    assert evidence["retrieved_at"] == tranche.RETRIEVED_AT


def test_raw_capture_is_closed_and_exact() -> None:
    directory = (
        tranche.resolve_external_capture(tranche.CAPTURE_ORIGIN, tranche.CAPTURE_TRASH)
    )
    tranche._validate_capture_directory(directory)
    assert len(tranche.CAPTURE_FILE_PINS) == 26
    assert sum(size for size, _digest in tranche.CAPTURE_FILE_PINS.values()) == (
        tranche.CAPTURE_TOTAL_BYTES
    )
    assert tranche.tree_digest(directory) == tranche.CAPTURE_TREE_SHA256


def test_beacon_point_is_review_only_and_exactly_untouched() -> None:
    witness = tranche._collision_witness(_live_source_document())
    beacon = witness["beacon_point_nonmutation"]
    assert beacon["sha256"] == tranche.BEACON_PIN[1]
    assert beacon["ctime_ns"] == tranche.BEACON_PIN[2]
    assert beacon["v92_lifecycle"] == "announced"
    assert beacon["mutated"] is False
    assert beacon["new_physical_observation_added"] is False
    assessment = tranche._candidate_assessment("2026-07-22T03:20:00Z")
    row = assessment["candidates"][1]
    assert row["decision"] == "review_only_existing_announced_record_unchanged"
    assert row["excluded_capacity_context_mw"] == [352, 500, 1000]
    assert row["normalized_entity"] is None
    assert row["normalized_lifecycle"] is None
    assert row["normalized_capacity"] is None


def test_v92_collision_witness_is_empty() -> None:
    witness = tranche._collision_witness(_live_source_document())
    assert witness["v92_selected_input_count"] == 485
    assert witness["v92_entity_count"] == 988
    assert witness["planned_distinct_stable_keys"] == 2
    assert witness["planned_distinct_evidence_keys"] == 3
    assert witness["exact_v92_stable_key_collisions"] == []
    assert witness["exact_v92_evidence_key_collisions"] == []
    assert witness["unexpected_source_collisions"] == {}


def test_private_stage_withdraws_final_source_and_replays_offline() -> None:
    if tranche.ARTIFACT.exists():
        assert tranche.validate_artifact()["curated_source_records"] == 1
        return
    recorded_at = (
        datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=30)
    ).isoformat().replace("+00:00", "Z")
    prepared = tranche._prepare(recorded_at)
    try:
        assert not tranche.SOURCE.exists()
        assert not tranche.ARTIFACT.exists()
        manifest = tranche.validate_artifact(
            prepared.artifact_stage,
            source_path=prepared.source_stage / tranche.SOURCE_FILENAME,
            require_live=False,
            require_frozen=False,
            wall_clock=tranche._instant(recorded_at),
        )
        assert manifest["curated_source_records"] == 1
        snapshot = json.loads(
            (prepared.artifact_stage / "source-snapshot.json").read_text()
        )
        assert snapshot["totals"]["distinct_entities"] == 2
        assert snapshot["totals"]["unique_evidence_records"] == 3
        assert snapshot["capacity_boundary"]["nonadditive"] is True
    finally:
        tranche._restore_author_draft(prepared)
    assert tranche.SOURCE.exists()
    assert stat.S_IMODE(tranche.SOURCE.stat().st_mode) == 0o644


def test_chmod_freeze_only_changes_staged_publication_members(
    tmp_path: Path,
) -> None:
    source_stage = tmp_path / "source-stage"
    artifact_stage = tmp_path / "artifact-stage"
    source_stage.mkdir()
    artifact_stage.mkdir()
    staged_source = source_stage / tranche.SOURCE_FILENAME
    staged_source.write_bytes(tranche.SOURCE.read_bytes())
    staged_source.chmod(0o600)
    document = tranche._read_document(staged_source)
    tranche._write_artifact_stage(
        artifact_stage, "2000-01-01T00:00:00Z", document
    )
    prepared = tranche._Prepared(
        source_stage, artifact_stage, "2000-01-01T00:00:00Z"
    )
    beacon_ctime = tranche.BEACON_SOURCE.stat().st_ctime_ns
    tranche._freeze_after_barrier(prepared)
    assert stat.S_IMODE(staged_source.stat().st_mode) == 0o444
    assert stat.S_IMODE(artifact_stage.stat().st_mode) == 0o555
    assert all(
        stat.S_IMODE(member.stat().st_mode) == 0o444
        for member in artifact_stage.iterdir()
    )
    assert tranche.BEACON_SOURCE.stat().st_ctime_ns == beacon_ctime


def test_partial_final_collision_fails_closed(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / tranche.SOURCE_FILENAME
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    monkeypatch.setattr(tranche, "SOURCE", source)
    monkeypatch.setattr(tranche, "ARTIFACT", artifact)
    with pytest.raises(tranche.Hut8RiverBendError, match="partial"):
        tranche.build(recorded_at="2099-01-01T00:00:00Z")


def test_late_collision_rolls_source_back_by_identity(
    tmp_path: Path, monkeypatch
) -> None:
    source_stage = tmp_path / "source-stage"
    artifact_stage = tmp_path / "artifact-stage"
    source_stage.mkdir()
    artifact_stage.mkdir()
    staged_source = source_stage / tranche.SOURCE_FILENAME
    staged_source.write_bytes(tranche.SOURCE.read_bytes())
    staged_source.chmod(0o600)
    tranche._write_artifact_stage(
        artifact_stage,
        "2099-01-01T00:00:00Z",
        tranche._read_document(staged_source),
    )
    final_source = tmp_path / "final-source.json"
    final_artifact = tmp_path / "final-artifact"
    monkeypatch.setattr(tranche, "SOURCE", final_source)
    monkeypatch.setattr(tranche, "ARTIFACT", final_artifact)
    monkeypatch.setattr(tranche, "_freeze_after_barrier", lambda _prepared: None)
    prepared = tranche._Prepared(
        source_stage, artifact_stage, "2099-01-01T00:00:00Z"
    )
    original = tranche._promote_noreplace
    calls = 0

    def collide(source: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise FileExistsError("injected River Bend collision")
        original(source, destination)

    monkeypatch.setattr(tranche, "_promote_noreplace", collide)
    with pytest.raises(FileExistsError, match="injected River Bend collision"):
        tranche._publish(prepared)
    assert staged_source.exists()
    assert not final_source.exists()
    assert not final_artifact.exists()


def test_artifact_rights_never_redistribute_raw_or_http_state() -> None:
    rights = json.loads(
        tranche._artifact_documents(
            "2026-07-22T03:20:00Z", _live_source_document()
        )["rights-and-disposition.json"]
    )
    assert rights["raw_capture_redistributed"] is False
    assert rights["raw_response_bodies_retained_in_artifact"] is False
    assert rights["raw_response_headers_retained_in_artifact"] is False
    assert rights["cookies_or_http_state_retained_in_artifact"] is False


def test_live_chronology_tamper_and_residue_after_publication(
    tmp_path: Path,
) -> None:
    if not tranche.ARTIFACT.exists():
        pytest.skip("River Bend artifact not published yet")
    manifest = tranche.validate_artifact()
    before = tranche._instant(manifest["recorded_at"]) - timedelta(microseconds=1)
    with pytest.raises(tranche.Hut8RiverBendError, match="recorded_at is not live"):
        tranche.validate_artifact(wall_clock=before)
    assert not tranche.PUBLICATION_LOCK.exists()
    assert not list(tranche.SOURCES_ROOT.glob(".hut8-river-bend-source.*"))
    assert not list(tranche.ARTIFACT_ROOT.glob(f".{tranche.ARTIFACT_ID}.*"))
    copied = tmp_path / "artifact-copy"
    shutil.copytree(tranche.ARTIFACT, copied)
    copied.chmod(0o755)
    target = copied / "source-snapshot.json"
    target.chmod(0o644)
    target.write_bytes(target.read_bytes() + b" ")
    target.chmod(0o444)
    copied.chmod(0o555)
    with pytest.raises(tranche.Hut8RiverBendError, match="manifest pin differs"):
        tranche.validate_artifact(copied)
