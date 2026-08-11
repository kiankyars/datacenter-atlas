from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import shutil
import stat

import pytest

try:
    from datacenter_atlas.datacenter_atlas import (
        goodman_databank_lax01_official_enrichment_20260722 as tranche,
    )
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import (  # type: ignore[no-redef]
        goodman_databank_lax01_official_enrichment_20260722 as tranche,
    )


def _live_source_document() -> dict[str, object]:
    mode = 0o444 if tranche.ARTIFACT.exists() else 0o644
    return tranche._validate_source(tranche.SOURCE, mode=mode)


def test_exact_source_identity_address_and_bytes() -> None:
    document = _live_source_document()
    assert tranche.SOURCE_PIN == (
        13_595,
        "fc07e93af6357b754ee6b03d052958e9f73201c177459cf1d2c19b4ca4a5ebf5",
    )
    assert document["schema_version"] == "1.0"
    assert document["campus"]["stable_key"] == tranche.CAMPUS_KEY
    assert document["project"]["stable_key"] == tranche.PROJECT_KEY
    assert {document[name]["address"] for name in ("campus", "project")} == {
        tranche.EXACT_ADDRESS
    }
    assert all(
        document[name][field] is None
        for name in ("campus", "project")
        for field in ("coordinates", "geometry")
    )


def test_existing_source_replay_has_exact_zero_entity_delta() -> None:
    assert tranche._offline_import(
        tranche.SOURCE, "2026-07-22T03:30:00Z"
    ) == {
        "entities": 2,
        "entity_snapshots": 4,
        "evidence": 3,
        "lifecycle_observations": 1,
        "operating_model_observations": 0,
        "workload_observations": 0,
        "capacity_estimates": 1,
        "new_entities_from_enrichment": 0,
        "new_evidence_from_enrichment": 2,
        "updated_entity_snapshots_from_enrichment": 2,
    }


def test_lifecycle_roles_and_classification_boundaries() -> None:
    document = _live_source_document()
    assert document["lifecycle"] == []
    assert document["operating_models"] == []
    assert document["workloads"] == []
    assert document["campus"]["roles"] == {"owner": ["Goodman DataBank JV"]}
    assert document["project"]["roles"] == {}
    assert "operator" not in document["campus"]["roles"]
    assert "operator" not in document["project"]["roles"]


def test_only_32mw_planned_critical_it_is_normalized() -> None:
    capacities = _live_source_document()["capacities"]
    assert [
        (
            row["entity"],
            row["metric"],
            row["stage"],
            row["base"],
            row["as_of_date"],
        )
        for row in capacities
    ] == [("project", "critical_it_mw", "planned", 32, "2026-03-17")]
    assert not {49.5, 6, 26, 1.5} & {row["base"] for row in capacities}


@pytest.mark.parametrize(
    "forbidden_metric",
    [
        "gross_facility_mw",
        "grid_connection_mw",
        "annual_energy_mwh",
        "generation_nameplate_mw",
        "pue",
        "wue_l_per_kwh",
    ],
)
def test_forbidden_metric_is_not_normalized(forbidden_metric: str) -> None:
    metrics = {row["metric"] for row in _live_source_document()["capacities"]}
    assert forbidden_metric not in metrics


@pytest.mark.parametrize(
    ("evidence_key", "body_name", "header_name"),
    [
        (
            tranche.DATABANK_EVIDENCE,
            "databank_lax01_press.body",
            "databank_lax01_press.headers",
        ),
        (
            tranche.BROCHURE_EVIDENCE,
            "goodman_lax01_brochure.body",
            "goodman_lax01_brochure.headers",
        ),
    ],
)
def test_evidence_has_exact_body_and_header_lineage(
    evidence_key: str, body_name: str, header_name: str
) -> None:
    evidence = {row["key"]: row for row in _live_source_document()["evidence"]}[
        evidence_key
    ]
    assert evidence["content_hash"] == tranche.CAPTURE_FILE_PINS[body_name][1]
    assert evidence["metadata"]["capture_headers_sha256"] == (
        tranche.CAPTURE_FILE_PINS[header_name][1]
    )
    assert evidence["retrieved_at"] == tranche.RETRIEVED_AT


def test_raw_capture_is_closed_exact_and_includes_both_403_headers() -> None:
    directory = (
        tranche.resolve_external_capture(tranche.CAPTURE_ORIGIN, tranche.CAPTURE_TRASH)
    )
    tranche._validate_capture_directory(directory)
    assert len(tranche.CAPTURE_FILE_PINS) == 8
    assert set(tranche.CAPTURE_FILE_PINS) >= {
        "goodman_ce_lax01_2026.headers",
        "goodman_lax01_topping_out.headers",
    }
    assert sum(size for size, _digest in tranche.CAPTURE_FILE_PINS.values()) == (
        tranche.CAPTURE_TOTAL_BYTES
    )
    assert tranche.tree_digest(directory) == tranche.CAPTURE_TREE_SHA256
    inventory = tranche._capture_inventory("2026-07-22T03:30:00Z")
    assert inventory["failed_header_only_captures"] == 2
    assert len(inventory["complete_private_file_inventory"]) == 8


def test_v93_identity_reuse_and_prior_lifecycle_lineage() -> None:
    witness = tranche._collision_witness(_live_source_document())
    assert witness["v93_selected_input_count"] == 488
    assert witness["v93_entity_count"] == 994
    assert witness["expected_v93_stable_key_reuse"] == sorted(
        [tranche.CAMPUS_KEY, tranche.PROJECT_KEY]
    )
    assert witness["planned_distinct_evidence_keys"] == 2
    assert witness["unexpected_source_collisions"] == {}
    prior = witness["prior_lax01_nonmutation"]
    assert prior["sha256"] == tranche.PRIOR_PIN[1]
    assert prior["ctime_ns"] == tranche.PRIOR_PIN[2]
    assert prior["v93_lifecycle"] == "mep_electrical"
    assert prior["v93_lifecycle_as_of_date"] == "2026-03-31"


def test_private_stage_withdraws_and_restores_exact_author_draft() -> None:
    if tranche.ARTIFACT.exists():
        assert tranche.validate_artifact()["curated_source_records"] == 1
        return
    before = tranche.SOURCE.read_bytes()
    recorded_at = (
        datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=30)
    ).isoformat().replace("+00:00", "Z")
    prepared = tranche._prepare(recorded_at)
    try:
        assert not tranche.SOURCE.exists()
        assert not tranche.ARTIFACT.exists()
        staged_source = prepared.source_stage / tranche.SOURCE_FILENAME
        assert staged_source.read_bytes() == before
        manifest = tranche.validate_artifact(
            prepared.artifact_stage,
            source_path=staged_source,
            require_live=False,
            require_frozen=False,
            wall_clock=tranche._instant(recorded_at),
        )
        assert manifest["governed_source"]["sha256"] == tranche.SOURCE_PIN[1]
    finally:
        tranche._restore_author_draft(prepared)
    assert tranche.SOURCE.read_bytes() == before
    assert stat.S_IMODE(tranche.SOURCE.stat().st_mode) == 0o644


def test_capture_after_declared_time_fails_and_restores_draft() -> None:
    if tranche.ARTIFACT.exists():
        pytest.skip("governed source already published")
    before = tranche.SOURCE.read_bytes()
    with pytest.raises(tranche.GoodmanLax01Error, match="post-dates"):
        tranche._prepare("2026-07-22T02:53:32Z")
    assert tranche.SOURCE.read_bytes() == before
    assert stat.S_IMODE(tranche.SOURCE.stat().st_mode) == 0o644


def test_source_semantic_tamper_fails_pin_before_acceptance(
    tmp_path: Path,
) -> None:
    document = _live_source_document()
    document["capacities"][0]["base"] = 49.5
    path = tmp_path / tranche.SOURCE_FILENAME
    path.write_text(json.dumps(document))
    path.chmod(0o600)
    with pytest.raises(tranche.GoodmanLax01Error, match="pinned file differs"):
        tranche._validate_source(path, mode=0o600)


def test_partial_final_collision_fails_closed(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / tranche.SOURCE_FILENAME
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    monkeypatch.setattr(tranche, "SOURCE", source)
    monkeypatch.setattr(tranche, "ARTIFACT", artifact)
    with pytest.raises(tranche.GoodmanLax01Error, match="partial"):
        tranche.build(recorded_at="2099-01-01T00:00:00Z")


def test_late_artifact_collision_rolls_promoted_source_back_by_identity(
    tmp_path: Path, monkeypatch
) -> None:
    source_stage = tmp_path / "source-stage"
    artifact_stage = tmp_path / "artifact-stage"
    source_stage.mkdir()
    artifact_stage.mkdir()
    staged_source = source_stage / tranche.SOURCE_FILENAME
    staged_source.write_bytes(tranche.SOURCE.read_bytes())
    staged_source.chmod(0o444)
    (artifact_stage / "placeholder").write_text("stage")
    final_source = tmp_path / "final-source.json"
    final_artifact = tmp_path / "final-artifact"
    monkeypatch.setattr(tranche, "SOURCE", final_source)
    monkeypatch.setattr(tranche, "ARTIFACT", final_artifact)
    monkeypatch.setattr(tranche, "_freeze_after_barrier", lambda _prepared: None)
    monkeypatch.setattr(
        tranche, "_finalize_artifact_after_source_promotion", lambda _prepared: None
    )
    prepared = tranche._Prepared(
        source_stage, artifact_stage, "2099-01-01T00:00:00Z"
    )
    original = tranche._promote_noreplace
    calls = 0

    def collide(source: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise FileExistsError("injected Goodman LAX01 collision")
        original(source, destination)

    monkeypatch.setattr(tranche, "_promote_noreplace", collide)
    with pytest.raises(FileExistsError, match="injected Goodman LAX01 collision"):
        tranche._publish(prepared)
    assert staged_source.exists()
    assert not final_source.exists()
    assert not final_artifact.exists()


def test_artifact_rights_never_redistribute_raw_or_http_state() -> None:
    source = tranche.SOURCE
    rights = json.loads(
        tranche._artifact_documents(
            "2026-07-22T03:30:00Z",
            _live_source_document(),
            source_final_ctime_ns=source.stat().st_ctime_ns,
        )["rights-and-disposition.json"]
    )
    assert rights["raw_capture_redistributed"] is False
    assert rights["raw_response_bodies_retained_in_artifact"] is False
    assert rights["raw_response_headers_retained_in_artifact"] is False
    assert rights["cookies_or_http_state_retained_in_artifact"] is False
    assert rights["failed_403_header_captures_inventoried"] == 2


def test_live_chronology_source_pin_tamper_and_residue_after_publication(
    tmp_path: Path,
) -> None:
    if not tranche.ARTIFACT.exists():
        pytest.skip("Goodman LAX01 artifact not published yet")
    manifest = tranche.validate_artifact()
    assert manifest["governed_source"] == {
        "bytes": tranche.SOURCE_PIN[0],
        "final_ctime_ns": tranche.SOURCE.stat().st_ctime_ns,
        "path": f"sources/{tranche.SOURCE_FILENAME}",
        "sha256": tranche.SOURCE_PIN[1],
    }
    before = tranche._instant(manifest["recorded_at"]) - timedelta(microseconds=1)
    with pytest.raises(tranche.GoodmanLax01Error, match="recorded_at is not live"):
        tranche.validate_artifact(wall_clock=before)
    assert not tranche.PUBLICATION_LOCK.exists()
    assert not list(
        tranche.SOURCES_ROOT.glob(".goodman-databank-lax01-source.*")
    )
    assert not list(tranche.ARTIFACT_ROOT.glob(f".{tranche.ARTIFACT_ID}.*"))
    copied = tmp_path / "artifact-copy"
    shutil.copytree(tranche.ARTIFACT, copied)
    copied.chmod(0o755)
    target = copied / "source-snapshot.json"
    target.chmod(0o644)
    target.write_bytes(target.read_bytes() + b" ")
    target.chmod(0o444)
    copied.chmod(0o555)
    with pytest.raises(tranche.GoodmanLax01Error, match="manifest pin differs"):
        tranche.validate_artifact(copied)

