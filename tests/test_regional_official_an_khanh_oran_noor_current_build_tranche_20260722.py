from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import shutil
import stat

import pytest

try:
    from datacenter_atlas.datacenter_atlas import (
        regional_official_an_khanh_oran_noor_current_build_tranche_20260722 as publication,
    )
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import (  # type: ignore[no-redef]
        regional_official_an_khanh_oran_noor_current_build_tranche_20260722 as publication,
    )


def _future(seconds: int = 30) -> str:
    return (
        (datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=seconds))
        .isoformat()
        .replace("+00:00", "Z")
    )


def _configure_private_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    sources = tmp_path / "sources"
    artifacts = tmp_path / "source_artifacts"
    sources.mkdir()
    artifacts.mkdir()
    monkeypatch.setattr(publication, "SOURCES_ROOT", sources)
    monkeypatch.setattr(publication, "ARTIFACT_ROOT", artifacts)
    monkeypatch.setattr(publication, "ARTIFACT", artifacts / publication.ARTIFACT_ID)
    monkeypatch.setattr(publication, "PUBLICATION_LOCK", tmp_path / ".lock")
    return sources, artifacts


def test_reviewed_stages_and_capture_are_exact_immutable_inputs() -> None:
    identities = publication._validate_reviewed_inputs()
    assert publication.tree_digest(publication.REVIEWED_SOURCE_STAGE) == (
        publication.REVIEWED_SOURCE_TREE_SHA256
    )
    assert publication.tree_digest(publication.REVIEWED_ARTIFACT_STAGE) == (
        publication.REVIEWED_ARTIFACT_TREE_SHA256
    )
    assert publication.tree_digest(publication.RAW_CAPTURE) == (
        publication.RAW_CAPTURE_TREE_SHA256
    )
    assert set(publication.REVIEWED_SOURCE_PINS) == set(publication.SOURCE_FILENAMES)
    assert len(publication.REVIEWED_ARTIFACT_PINS) == 7
    assert len(publication.RAW_CAPTURE_PINS) == 9
    assert stat.S_IMODE(publication.REVIEWED_SOURCE_STAGE.stat().st_mode) == 0o700
    assert stat.S_IMODE(publication.REVIEWED_ARTIFACT_STAGE.stat().st_mode) == (0o700)
    assert stat.S_IMODE(publication.RAW_CAPTURE.stat().st_mode) == 0o555
    publication._assert_reviewed_input_identities(identities)


def test_accepted_source_bytes_are_distinct_and_preserve_sparse_boundaries() -> None:
    documents = publication.expected_source_documents()
    assert tuple(documents) == publication.SOURCE_FILENAMES
    expected_pins = {
        publication.AN_KHANH_SOURCE_FILENAME: (
            5_538,
            "fe220d936abcef27f2099123d4486a541385b97c4ded69ea2fd4c4078177b8d1",
        ),
        publication.ORAN_SOURCE_FILENAME: (
            7_401,
            "d71be15c1fb19d3c1d90d6341dcbf809f7c2ab9c24b2afc252c09d902020b3b8",
        ),
        publication.NOOR_SOURCE_FILENAME: (
            4_951,
            "9b771b6e0817d68c010775c5f8a2f45745279a30bddef3666ea975418ac7dbbc",
        ),
    }
    assert sum(len(document["evidence"]) for document in documents.values()) == 4
    assert sum(len(document["lifecycle"]) for document in documents.values()) == 3
    for name, document in documents.items():
        raw = publication._canonical(document)
        assert (len(raw), publication._sha256_bytes(raw)) == expected_pins[name]
        assert expected_pins[name] != publication.REVIEWED_SOURCE_PINS[name]
        text = raw.decode("utf-8")
        assert publication.ARTIFACT_ID in text
        assert "prepublication" not in text.lower()
        assert document["operating_models"] == []
        assert document["workloads"] == []
        assert document["capacities"] == []
        for entity in ("campus", "project"):
            assert document[entity]["coordinates"] is None
            assert document[entity]["geometry"] is None

    an_khanh = documents[publication.AN_KHANH_SOURCE_FILENAME]
    design = an_khanh["evidence"][0]["metadata"]["design_power_not_normalized"]
    assert design["value"] == 60
    assert design["typing"] == "untyped_design_metadata_only"
    assert design["capacity_row_created"] is False
    assert documents[publication.ORAN_SOURCE_FILENAME]["project"]["roles"] == {}
    assert (
        documents[publication.NOOR_SOURCE_FILENAME]["lifecycle"][0]["as_of_date"]
        == "2026-07-22"
    )


def test_accepted_artifact_uses_final_paths_and_rejects_bolivia() -> None:
    recorded_at = "2026-07-22T05:00:00Z"
    documents = publication.expected_source_documents()
    payloads = publication._artifact_documents(recorded_at, documents)
    snapshot = json.loads(payloads["source-snapshot.json"])
    assessment = json.loads(payloads["candidate-assessment.json"])
    assert snapshot["integration"] == {
        "published": True,
        "accepted": True,
        "open_seed_successor_created": False,
        "release_integration": "none",
        "federation_integration": "none",
        "identity_integration": "none",
        "timeline_integration": "none",
        "construction_master_integration": "none",
        "map_integration": "none",
        "coverage_integration": "none",
        "downstream_files_touched": [],
    }
    assert snapshot["totals"]["facility_type_observations"] == 0
    assert snapshot["totals"]["workload_observations"] == 0
    assert snapshot["totals"]["capacity_estimates"] == 0
    assert snapshot["totals"]["energy_consumption_observations"] == 0
    assert snapshot["totals"]["coordinate_observations"] == 0
    assert all(
        row["path"].startswith("sources/")
        and row["accepted"] is True
        and row["published"] is True
        for row in snapshot["source_records"]
    )
    bolivia = next(
        row
        for row in assessment["candidates"]
        if row["candidate_id"] == "bolivia-fiscalia-data-center"
    )
    assert bolivia["decision"] == ("rejected_review_only_unhashable_official_timeout")
    assert bolivia["source_paths"] == []
    assert bolivia["accepted"] is False
    assert bolivia["published"] is False
    assert bolivia["rejected"] is True
    assert bolivia["stable_key_created"] is False
    assert bolivia["evidence_record_created"] is False
    assert bolivia["lifecycle_claim_created"] is False
    assert bolivia["timeout_capture"]["completed_timeout_attempts"] == 2
    assert bolivia["timeout_capture"]["response_header_bytes"] == 0
    assert bolivia["timeout_capture"]["response_body_bytes"] == 0
    assert bolivia["timeout_capture"]["content_hash"] is None
    for name, raw in payloads.items():
        if name != "source-snapshot.json":
            assert "prepublication" not in raw.decode("utf-8").lower()
            assert "prospective-sources/" not in raw.decode("utf-8").lower()
    lineage = snapshot["reviewed_candidate_lineage"]
    assert lineage["artifact_id"] == publication.REVIEWED_CANDIDATE_ID
    assert lineage["direct_promotion_of_candidate_bytes"] is False
    assert lineage["artifact_storage_path_redacted"] is True
    assert lineage["source_storage_path_redacted"] is True
    assert lineage["raw_capture_storage_path_redacted"] is True
    assert "artifact_stage" not in lineage
    assert "source_stage" not in lineage
    assert "raw_capture_directory" not in lineage
    assert all(
        "/Users/" not in raw.decode("utf-8") and "/private/" not in raw.decode("utf-8")
        for raw in payloads.values()
    )


def test_default_authorization_fails_closed_and_private_finals_are_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_private_publication(tmp_path, monkeypatch)
    assert not publication.ARTIFACT.exists()
    assert not any(path.exists() for path in publication._final_source_paths().values())
    with pytest.raises(
        publication.RegionalPublicationError,
        match="publication_authorized=True",
    ):
        publication.build()
    assert not publication.ARTIFACT.exists()
    assert not any(path.exists() for path in publication._final_source_paths().values())


def test_disposable_preflight_is_deterministic_frozen_and_discarded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_private_publication(tmp_path, monkeypatch)
    recorded_at = _future(90)
    first = publication.preflight(recorded_at=recorded_at)
    second = publication.preflight(recorded_at=recorded_at)
    for key in (
        "artifact_manifest_sha256",
        "artifact_tree_sha256",
        "source_tree_sha256",
        "source_pins",
        "rows",
    ):
        assert first[key] == second[key]
    assert first["status"] == "PREFLIGHT_VALIDATED_AND_DISCARDED"
    assert first["published"] is False
    assert first["source_stage_discarded"] is True
    assert first["artifact_stage_discarded"] is True
    assert first["reviewed_source_stage_retained"] is True
    assert first["reviewed_artifact_stage_retained"] is True
    assert first["raw_capture_retained"] is True
    assert first["final_artifact_exists"] is False
    assert first["final_source_exists"] is False
    assert first["rows"] == {
        "entity_snapshots": 6,
        "evidence": 4,
        "lifecycle": 3,
        "facility_types": 0,
        "operating_models": 0,
        "workloads": 0,
        "capacities": 0,
        "energy_consumption": 0,
        "coordinates": 0,
        "geometry": 0,
    }
    assert not publication.ARTIFACT.exists()
    assert not any(path.exists() for path in publication._final_source_paths().values())


def test_authorized_private_root_publication_and_existing_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, _artifacts = _configure_private_publication(tmp_path, monkeypatch)
    recorded_at = _future(2)
    first = publication.build(recorded_at=recorded_at, publication_authorized=True)
    assert first["status"] == "published"
    assert first["published"] is True
    assert publication.ARTIFACT.is_dir()
    assert all((sources / name).is_file() for name in publication.SOURCE_FILENAMES)
    assert not publication.PUBLICATION_LOCK.exists()
    assert not list(sources.glob(".regional-an-khanh-oran-noor-source-stage-*"))
    target = publication._instant(recorded_at).timestamp()
    governed = (
        publication.ARTIFACT,
        *publication.ARTIFACT.rglob("*"),
        *publication._final_source_paths().values(),
    )
    for path in governed:
        metadata = path.stat(follow_symlinks=False)
        birth = getattr(metadata, "st_birthtime", metadata.st_ctime)
        assert max(birth, metadata.st_mtime) <= target + 0.000_001
        assert metadata.st_ctime + 0.000_001 >= target
    second = publication.build(recorded_at=recorded_at, publication_authorized=True)
    assert second["status"] == "existing-identical"
    assert second["manifest_sha256"] == first["manifest_sha256"]
    assert second["artifact_tree_sha256"] == first["artifact_tree_sha256"]


def test_private_root_artifact_failure_rolls_back_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, artifacts = _configure_private_publication(tmp_path, monkeypatch)
    real_promote = publication._promote_noreplace

    def fail_artifact(source: Path, destination: Path) -> None:
        if destination == publication.ARTIFACT:
            raise publication.RegionalPublicationError("injected artifact failure")
        real_promote(source, destination)

    monkeypatch.setattr(publication, "_promote_noreplace", fail_artifact)
    with pytest.raises(
        publication.RegionalPublicationError, match="injected artifact failure"
    ):
        publication.build(recorded_at=_future(2), publication_authorized=True)
    assert not publication.ARTIFACT.exists()
    assert not any((sources / name).exists() for name in publication.SOURCE_FILENAMES)
    assert not publication.PUBLICATION_LOCK.exists()
    assert not list(sources.iterdir())
    assert not list(artifacts.iterdir())


def test_private_root_partial_collision_fails_before_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, artifacts = _configure_private_publication(tmp_path, monkeypatch)
    (sources / publication.AN_KHANH_SOURCE_FILENAME).write_text("collision")
    with pytest.raises(
        publication.RegionalPublicationError, match="partial final-path collision"
    ):
        publication.build(recorded_at=_future(30), publication_authorized=True)
    assert len(list(sources.iterdir())) == 1
    assert not list(artifacts.iterdir())
    assert not publication.PUBLICATION_LOCK.exists()


def test_reviewed_input_tamper_fails_without_touching_real_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_stage = publication.REVIEWED_SOURCE_STAGE
    copied = tmp_path / "reviewed-sources"
    shutil.copytree(real_stage, copied)
    copied.chmod(0o700)
    for path in copied.iterdir():
        path.chmod(0o600)
    target = copied / publication.AN_KHANH_SOURCE_FILENAME
    target.write_bytes(target.read_bytes() + b"\n")
    monkeypatch.setattr(publication, "REVIEWED_SOURCE_STAGE", copied)
    with pytest.raises(
        publication.RegionalPublicationError, match="pinned input differs"
    ):
        publication._validate_reviewed_inputs()
    publication._pin(
        real_stage / publication.AN_KHANH_SOURCE_FILENAME,
        publication.REVIEWED_SOURCE_PINS[publication.AN_KHANH_SOURCE_FILENAME],
        mode=0o600,
    )


def test_temporal_and_lock_identity_guards_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "payload").write_text("x")
    target = datetime.now(UTC) - timedelta(seconds=10)
    with pytest.raises(
        publication.RegionalPublicationError, match="post-dates recorded_at"
    ):
        publication._assert_stage_precedes(stage, target)

    lock = tmp_path / ".publication-lock"
    monkeypatch.setattr(publication, "PUBLICATION_LOCK", lock)
    with pytest.raises(
        publication.RegionalPublicationError, match="substituted.*lock cleanup"
    ):
        with publication._publication_lock():
            lock.unlink()
            lock.write_text("replacement")
    assert lock.read_text() == "replacement"
    lock.unlink()


def test_preflight_never_moves_reviewed_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_private_publication(tmp_path, monkeypatch)
    before = (
        publication._identity(publication.REVIEWED_SOURCE_STAGE, directory=True),
        publication._identity(publication.REVIEWED_ARTIFACT_STAGE, directory=True),
        publication._identity(publication.RAW_CAPTURE, directory=True),
    )
    publication.preflight(recorded_at=_future(60))
    after = (
        publication._identity(publication.REVIEWED_SOURCE_STAGE, directory=True),
        publication._identity(publication.REVIEWED_ARTIFACT_STAGE, directory=True),
        publication._identity(publication.RAW_CAPTURE, directory=True),
    )
    assert after == before
    assert not publication.ARTIFACT.exists()
