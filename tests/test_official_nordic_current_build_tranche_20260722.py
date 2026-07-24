from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import shutil

import pytest

try:
    from datacenter_atlas.datacenter_atlas import (
        official_nordic_current_build_tranche_20260722 as publication,
    )
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import (  # type: ignore[no-redef]
        official_nordic_current_build_tranche_20260722 as publication,
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


def test_reviewed_candidate_stages_and_raw_capture_are_exact_inputs() -> None:
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
    assert len(publication.RAW_CAPTURE_PINS) == 12
    publication._assert_reviewed_input_identities(identities)


def test_final_source_bytes_are_distinct_accepted_records() -> None:
    documents = publication.expected_source_documents()
    assert tuple(documents) == publication.SOURCE_FILENAMES
    expected_pins = {
        publication.XTX_SOURCE_FILENAME: (
            7_793,
            "dfd8908152eb6b6c937ba4c0b1ced909685733d90ab50e1a826b3e23ca937976",
        ),
        publication.SKYGARD_SOURCE_FILENAME: (
            7_152,
            "77fc3d8b702b06eb6f5941d08f12ef542ee5d545184e33a43fb2b3ab917291ad",
        ),
        publication.FIN04_SOURCE_FILENAME: (
            19_173,
            "ccba18dd2b8398c775e1b435830037a29e027482518c125419607ebcdb1e470e",
        ),
    }
    for name, document in documents.items():
        raw = publication._canonical(document)
        assert (len(raw), publication._sha256_bytes(raw)) == expected_pins[name]
        assert expected_pins[name] != publication.REVIEWED_SOURCE_PINS[name]
        assert publication.ARTIFACT_ID in raw.decode("utf-8")
        assert "prepublication" not in raw.decode("utf-8").lower()
        assert document["schema_version"] == "1.1"
        assert document["capacities"] == []
        assert document["workloads"] == []
        for entity in ("campus", "project"):
            assert document[entity]["coordinates"] is None
            assert document[entity]["geometry"] is None


def test_final_artifact_uses_final_paths_and_accepted_truth_only() -> None:
    recorded_at = "2026-07-22T04:45:00Z"
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
    assert all(
        row["path"].startswith("sources/")
        and row["accepted"] is True
        and row["published"] is True
        for row in snapshot["source_records"]
    )
    assert assessment["accepted_source_record_count"] == 3
    assert assessment["published_source_record_count"] == 3
    third = next(
        row
        for row in assessment["candidates"]
        if row["candidate_id"] == "xtx-kajaani-third-data-center"
    )
    assert third["source_paths"] == []
    assert third["accepted"] is False
    assert third["published"] is False
    for name, raw in payloads.items():
        if name != "source-snapshot.json":
            assert "prepublication" not in raw.decode("utf-8").lower()
            assert "prospective-sources/" not in raw.decode("utf-8").lower()
    lineage = snapshot["reviewed_candidate_lineage"]
    assert lineage["artifact_id"] == publication.REVIEWED_CANDIDATE_ID
    assert lineage["direct_promotion_of_candidate_bytes"] is False


def test_default_publication_authorization_fails_closed_and_changes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_private_publication(tmp_path, monkeypatch)
    assert not publication.ARTIFACT.exists()
    assert not any(path.exists() for path in publication._final_source_paths().values())
    with pytest.raises(
        publication.NordicPublicationError,
        match="publication_authorized=True",
    ):
        publication.build()
    assert not publication.ARTIFACT.exists()
    assert not any(path.exists() for path in publication._final_source_paths().values())


def test_private_preflight_is_deterministic_frozen_and_fully_discarded(
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
    assert not publication.ARTIFACT.exists()
    assert not any(path.exists() for path in publication._final_source_paths().values())


def test_full_authorized_private_publication_and_existing_identical(
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
    assert not list(sources.glob(".official-nordic-current-build-source-stage-*"))
    second = publication.build(recorded_at=recorded_at, publication_authorized=True)
    assert second["status"] == "existing-identical"
    assert second["manifest_sha256"] == first["manifest_sha256"]
    assert second["artifact_tree_sha256"] == first["artifact_tree_sha256"]


def test_authorized_publication_rolls_back_source_promotions_on_artifact_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, artifacts = _configure_private_publication(tmp_path, monkeypatch)
    real_promote = publication._promote_noreplace

    def fail_artifact(source: Path, destination: Path) -> None:
        if destination == publication.ARTIFACT:
            raise publication.NordicPublicationError("injected artifact failure")
        real_promote(source, destination)

    monkeypatch.setattr(publication, "_promote_noreplace", fail_artifact)
    with pytest.raises(
        publication.NordicPublicationError, match="injected artifact failure"
    ):
        publication.build(recorded_at=_future(2), publication_authorized=True)
    assert not publication.ARTIFACT.exists()
    assert not any((sources / name).exists() for name in publication.SOURCE_FILENAMES)
    assert not publication.PUBLICATION_LOCK.exists()
    assert not list(sources.iterdir())
    assert not list(artifacts.iterdir())


def test_partial_final_collision_fails_before_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, artifacts = _configure_private_publication(tmp_path, monkeypatch)
    (sources / publication.XTX_SOURCE_FILENAME).write_text("collision")
    with pytest.raises(
        publication.NordicPublicationError, match="partial final-path collision"
    ):
        publication.build(recorded_at=_future(30), publication_authorized=True)
    assert len(list(sources.iterdir())) == 1
    assert not list(artifacts.iterdir())
    assert not publication.PUBLICATION_LOCK.exists()


def test_reviewed_input_tamper_fails_closed_without_touching_real_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_stage = publication.REVIEWED_SOURCE_STAGE
    copied = tmp_path / "reviewed-sources"
    shutil.copytree(real_stage, copied)
    copied.chmod(0o700)
    for path in copied.iterdir():
        path.chmod(0o600)
    target = copied / publication.XTX_SOURCE_FILENAME
    target.write_bytes(target.read_bytes() + b"\n")
    monkeypatch.setattr(publication, "REVIEWED_SOURCE_STAGE", copied)
    with pytest.raises(
        publication.NordicPublicationError, match="pinned input differs"
    ):
        publication._validate_reviewed_inputs()
    publication._pin(
        real_stage / publication.XTX_SOURCE_FILENAME,
        publication.REVIEWED_SOURCE_PINS[publication.XTX_SOURCE_FILENAME],
        mode=0o600,
    )


def test_stage_time_and_lock_identity_guards_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stage = tmp_path / "stage"
    stage.mkdir()
    payload = stage / "payload"
    payload.write_text("x")
    target = datetime.now(UTC) - timedelta(seconds=10)
    with pytest.raises(
        publication.NordicPublicationError, match="post-dates recorded_at"
    ):
        publication._assert_stage_precedes(stage, target)

    lock = tmp_path / ".publication-lock"
    monkeypatch.setattr(publication, "PUBLICATION_LOCK", lock)
    with pytest.raises(
        publication.NordicPublicationError, match="substituted.*lock cleanup"
    ):
        with publication._publication_lock():
            lock.unlink()
            lock.write_text("replacement")
    assert lock.read_text() == "replacement"
    lock.unlink()


def test_preflight_does_not_remove_or_move_review_inputs(
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
