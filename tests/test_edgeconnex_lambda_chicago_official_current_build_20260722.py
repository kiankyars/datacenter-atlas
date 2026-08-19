from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import shutil
import stat

import pytest

try:
    from datacenter_atlas.datacenter_atlas import (
        edgeconnex_lambda_chicago_official_current_build_20260722 as publication,
    )
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import (  # type: ignore[no-redef]
        edgeconnex_lambda_chicago_official_current_build_20260722 as publication,
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


def test_reviewed_stages_and_optional_capture_clone_are_exact() -> None:
    identities = publication._validate_reviewed_inputs()
    assert publication.tree_digest(publication.REVIEWED_SOURCE_STAGE) == (
        publication.REVIEWED_SOURCE_TREE_SHA256
    )
    assert publication.tree_digest(publication.REVIEWED_ARTIFACT_STAGE) == (
        publication.REVIEWED_ARTIFACT_TREE_SHA256
    )
    assert stat.S_IMODE(publication.REVIEWED_SOURCE_STAGE.stat().st_mode) == 0o700
    assert stat.S_IMODE(publication.REVIEWED_ARTIFACT_STAGE.stat().st_mode) == 0o700
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o600
        for path in publication.REVIEWED_SOURCE_STAGE.iterdir()
    )
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o600
        for path in publication.REVIEWED_ARTIFACT_STAGE.iterdir()
    )
    if identities.capture_path is None:
        assert identities.captures == {}
    else:
        assert publication.tree_digest(identities.capture_path) == (
            publication.RAW_CAPTURE_TREE_SHA256
        )
        assert stat.S_IMODE(identities.capture_path.stat().st_mode) == 0o555
        assert all(
            stat.S_IMODE(path.stat().st_mode) == 0o444
            for path in identities.capture_path.iterdir()
        )
    assert set(publication.REVIEWED_SOURCE_PINS) == {publication.SOURCE_FILENAME}
    assert len(publication.REVIEWED_ARTIFACT_PINS) == 7
    assert len(publication.RAW_CAPTURE_PINS) == 28
    assert sum(pin[0] for pin in publication.RAW_CAPTURE_PINS.values()) == 6_524_603
    publication._assert_reviewed_input_identities(identities)


def test_accepted_source_is_byte_identical_and_preserves_guardrails() -> None:
    payload = publication.expected_source_bytes()
    reviewed = publication.REVIEWED_SOURCE_STAGE / publication.SOURCE_FILENAME
    document = json.loads(payload)
    assert payload == reviewed.read_bytes()
    assert (len(payload), publication._sha256_bytes(payload)) == (
        publication.REVIEWED_SOURCE_PINS[publication.SOURCE_FILENAME]
    )
    assert publication._canonical(document) == payload
    assert document["campus"]["stable_key"] == publication.CAMPUS_KEY
    assert document["project"]["stable_key"] == publication.PROJECT_KEY
    assert document["lifecycle"] == [
        {
            "as_of_date": "2025-08-21",
            "confidence": 0.98,
            "entity": "project",
            "evidence_key": "edgeconnex-lambda-chicago-build-2025-08-21",
            "method": "authoritative_physical_status_update",
            "value": "under_construction",
        }
    ]
    assert document["operating_models"] == []
    assert document["capacities"] == []
    assert [row["value"] for row in document["workloads"]] == [
        "hpc",
        "ai_training",
        "ai_inference",
    ]
    assert document["campus"]["roles"] == {
        "developer": ["EdgeConneX"],
        "tenant": ["Lambda"],
    }
    for entity in ("campus", "project"):
        assert document[entity]["coordinates"] is None
        assert document[entity]["geometry"] is None


def test_artifact_has_one_acceptance_nine_review_only_and_hash_lineage() -> None:
    recorded_at = "2099-01-01T00:00:00Z"
    source_payload = publication.expected_source_bytes()
    payloads = publication._artifact_documents(
        recorded_at, json.loads(source_payload), source_payload
    )
    snapshot = json.loads(payloads["source-snapshot.json"])
    assessment = json.loads(payloads["acceptance-assessment.json"])
    assert len(assessment["assessments"]) == 10
    accepted = [row for row in assessment["assessments"] if row["accepted"]]
    assert [row["assessment_id"] for row in accepted] == [
        publication.ACCEPTED_ASSESSMENT_ID
    ]
    review_only = [row for row in assessment["assessments"] if not row["accepted"]]
    assert len(review_only) == 9
    assert all(row["source_paths"] == [] for row in review_only)
    assert all(row["published"] is False for row in review_only)
    assert all(row["seeded"] is False for row in assessment["assessments"])
    assert snapshot["source_records"] == [
        publication._source_record(json.loads(source_payload), source_payload)
    ]
    assert snapshot["integration"] == {
        "published": True,
        "accepted": True,
        "open_seed_source_created": False,
        "release_integration": "none",
        "federation_integration": "none",
        "identity_integration": "none",
        "timeline_integration": "none",
        "construction_master_integration": "none",
        "map_integration": "none",
        "coverage_integration": "none",
        "downstream_files_touched": [],
    }
    lineage = snapshot["reviewed_input_lineage"]
    assert lineage["purpose"] == "reviewed_input_hash_lineage_only"
    assert (
        lineage["reviewed_source_sha256"]
        == (publication.REVIEWED_SOURCE_PINS[publication.SOURCE_FILENAME][1])
    )
    assert lineage["reviewed_artifact_tree_sha256"] == (
        publication.REVIEWED_ARTIFACT_TREE_SHA256
    )
    assert lineage["capture_tree_sha256"] == publication.RAW_CAPTURE_TREE_SHA256
    assert not any("path" in key for key in lineage)


def test_all_accepted_bytes_remove_restricted_language_and_internal_paths() -> None:
    source_payload = publication.expected_source_bytes()
    payloads = publication._artifact_documents(
        "2099-01-01T00:00:00Z", json.loads(source_payload), source_payload
    )
    for payload in (source_payload, *payloads.values()):
        lowered = payload.decode("utf-8").lower()
        for fragment in publication.FORBIDDEN_PUBLICATION_FRAGMENTS:
            assert fragment not in lowered
        assert publication.RAW_CAPTURE.name.lower() not in lowered
        assert publication.REVIEWED_SOURCE_STAGE.name.lower() not in lowered
        assert publication.REVIEWED_ARTIFACT_STAGE.name.lower() not in lowered
    inventory = json.loads(payloads["retrieval-inventory.json"])
    rights = json.loads(payloads["rights-and-disposition.json"])
    assert "capture_bundle_id" not in inventory
    assert inventory["capture_storage_location_redacted"] is True
    assert rights["capture_storage_location_redacted"] is True


def test_default_authorization_fails_closed_and_changes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_private_publication(tmp_path, monkeypatch)
    before = publication._validate_reviewed_inputs()
    with pytest.raises(
        publication.EdgeConneXPublicationError,
        match="publication_authorized=True",
    ):
        publication.build()
    publication._assert_reviewed_input_identities(before)
    assert not publication.ARTIFACT.exists()
    assert not publication._final_source().exists()


def test_preflight_imports_exactly_twice_is_deterministic_and_discards(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_private_publication(tmp_path, monkeypatch)
    monkeypatch.setattr(publication, "_resolve_raw_capture", lambda: None)
    calls = 0
    original = publication.CuratedOfficialSourceAdapterV11.import_file

    def counted_import(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(
        publication.CuratedOfficialSourceAdapterV11,
        "import_file",
        counted_import,
    )
    recorded_at = "2099-01-01T00:00:00Z"
    result = publication.preflight(recorded_at=recorded_at)
    assert calls == 2
    assert result["offline_imports"] == 2
    assert result["status"] == "PREFLIGHT_VALIDATED_AND_DISCARDED"
    assert result["published"] is False
    assert result["source_stage_discarded"] is True
    assert result["artifact_stage_discarded"] is True
    assert result["reviewed_source_stage_retained"] is True
    assert result["reviewed_artifact_stage_retained"] is True
    assert result["capture_clone_retained"] is False
    assert not publication.ARTIFACT.exists()
    assert not publication._final_source().exists()

    calls = 0
    repeated = publication.preflight(recorded_at=recorded_at)
    assert calls == 2
    for key in (
        "artifact_manifest_sha256",
        "artifact_tree_sha256",
        "artifact_pins",
        "source_tree_sha256",
        "source_pins",
        "modes",
        "rows",
    ):
        assert result[key] == repeated[key]


def test_prepare_uses_unique_same_filesystem_stages_and_recursive_time_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_private_publication(tmp_path, monkeypatch)
    recorded_at = "2099-01-01T00:00:00Z"
    first = publication._prepare(recorded_at)
    second = publication._prepare(recorded_at)
    try:
        assert first.source_stage != second.source_stage
        assert first.artifact_stage != second.artifact_stage
        assert first.source_stage.parent == publication.SOURCES_ROOT
        assert first.artifact_stage.parent == publication.ARTIFACT_ROOT
        assert (
            first.source_stage.stat().st_dev == publication.SOURCES_ROOT.stat().st_dev
        )
        assert (
            first.artifact_stage.stat().st_dev
            == publication.ARTIFACT_ROOT.stat().st_dev
        )
        target = publication._instant(recorded_at)
        publication._assert_stage_precedes(first.source_stage, target)
        publication._assert_stage_precedes(first.artifact_stage, target)
        assert set(first.source_identities) == {".", publication.SOURCE_FILENAME}
        assert set(first.artifact_identities) == {".", *publication.CLOSED_FILES}
    finally:
        for prepared in (first, second):
            publication._discard_owned_tree(
                prepared.source_stage, expected=prepared.source_identities
            )
            publication._discard_owned_tree(
                prepared.artifact_stage, expected=prepared.artifact_identities
            )


def test_source_stage_identity_failure_is_inside_cleanup_envelope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, artifacts = _configure_private_publication(tmp_path, monkeypatch)
    original = publication._identity
    injected = False

    def fail_new_source_once(
        path: Path, *, directory: bool | None = None
    ) -> tuple[int, int]:
        nonlocal injected
        if (
            not injected
            and directory is True
            and path.parent == sources
            and path.name.startswith(".edgeconnex-lambda-current-build-source-stage-")
        ):
            injected = True
            raise OSError("injected source-stage identity failure")
        return original(path, directory=directory)

    monkeypatch.setattr(publication, "_identity", fail_new_source_once)
    with pytest.raises(OSError, match="injected source-stage identity failure"):
        publication.preflight(recorded_at="2099-01-01T00:00:00Z")
    assert injected is True
    assert not list(sources.iterdir())
    assert not list(artifacts.iterdir())


def test_second_stage_allocation_failure_discards_first_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, artifacts = _configure_private_publication(tmp_path, monkeypatch)
    real_mkdtemp = publication.tempfile.mkdtemp
    calls = 0

    def fail_second(*args: object, **kwargs: object) -> str:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected artifact-stage allocation failure")
        return real_mkdtemp(*args, **kwargs)

    monkeypatch.setattr(publication.tempfile, "mkdtemp", fail_second)
    with pytest.raises(OSError, match="injected artifact-stage allocation failure"):
        publication.preflight(recorded_at="2099-01-01T00:00:00Z")
    assert not list(sources.iterdir())
    assert not list(artifacts.iterdir())


@pytest.mark.parametrize("failure", ["write", "fsync"])
def test_lock_initialization_failure_closes_fd_and_removes_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    lock = tmp_path / ".publication-lock"
    monkeypatch.setattr(publication, "PUBLICATION_LOCK", lock)
    real_write = publication.os.write
    real_fsync = publication.os.fsync

    def fail_write(descriptor: int, payload: bytes) -> int:
        raise OSError("injected lock write failure")

    def fail_fsync(descriptor: int) -> None:
        raise OSError("injected lock fsync failure")

    if failure == "write":
        monkeypatch.setattr(publication.os, "write", fail_write)
    else:
        monkeypatch.setattr(publication.os, "fsync", fail_fsync)
    with pytest.raises(OSError, match=f"injected lock {failure} failure"):
        with publication._publication_lock():
            raise AssertionError("lock body must not run")
    assert not lock.exists()

    monkeypatch.setattr(publication.os, "write", real_write)
    monkeypatch.setattr(publication.os, "fsync", real_fsync)
    with publication._publication_lock():
        assert lock.exists()
    assert not lock.exists()


def test_authorized_private_publication_existing_identical_and_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, _artifacts = _configure_private_publication(tmp_path, monkeypatch)
    recorded_at = _future(3)
    first = publication.build(recorded_at=recorded_at, publication_authorized=True)
    assert first["status"] == "published"
    assert first["published"] is True
    final_source = sources / publication.SOURCE_FILENAME
    assert final_source.read_bytes() == publication.expected_source_bytes()
    assert stat.S_IMODE(publication.ARTIFACT.stat().st_mode) == 0o555
    assert stat.S_IMODE(final_source.stat().st_mode) == 0o444
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o444
        for path in publication.ARTIFACT.iterdir()
    )
    target = publication._instant(recorded_at)
    publication._assert_stage_precedes(final_source, target)
    publication._assert_stage_precedes(publication.ARTIFACT, target)
    publication._assert_recursive_ctimes_at_or_after(final_source, target)
    publication._assert_recursive_ctimes_at_or_after(publication.ARTIFACT, target)
    assert not publication.PUBLICATION_LOCK.exists()
    assert not list(sources.glob(".edgeconnex-lambda-current-build-source-stage-*"))

    second = publication.build(recorded_at=recorded_at, publication_authorized=True)
    assert second["status"] == "existing-identical"
    assert second["manifest_sha256"] == first["manifest_sha256"]
    assert publication.validate_published()["status"] == "existing-identical"

    publication._discard_owned_tree(publication.ARTIFACT)
    with pytest.raises(
        publication.EdgeConneXPublicationError,
        match="partial final-path collision",
    ):
        publication.validate_published()


def test_artifact_failure_rolls_back_source_and_discards_stages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, artifacts = _configure_private_publication(tmp_path, monkeypatch)
    real_promote = publication._promote_noreplace

    def fail_artifact(source: Path, destination: Path) -> None:
        if destination == publication.ARTIFACT:
            raise publication.EdgeConneXPublicationError(
                "injected artifact promotion failure"
            )
        real_promote(source, destination)

    monkeypatch.setattr(publication, "_promote_noreplace", fail_artifact)
    with pytest.raises(
        publication.EdgeConneXPublicationError,
        match="injected artifact promotion failure",
    ):
        publication.build(recorded_at=_future(3), publication_authorized=True)
    assert not publication.ARTIFACT.exists()
    assert not (sources / publication.SOURCE_FILENAME).exists()
    assert not publication.PUBLICATION_LOCK.exists()
    assert not list(sources.iterdir())
    assert not list(artifacts.iterdir())


def test_partial_final_collision_fails_before_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, artifacts = _configure_private_publication(tmp_path, monkeypatch)
    collision = sources / publication.SOURCE_FILENAME
    collision.write_text("collision", encoding="utf-8")
    with pytest.raises(
        publication.EdgeConneXPublicationError,
        match="partial final-path collision",
    ):
        publication.build(recorded_at=_future(), publication_authorized=True)
    assert list(sources.iterdir()) == [collision]
    assert not list(artifacts.iterdir())
    assert not publication.PUBLICATION_LOCK.exists()


def test_no_replace_late_collision_fails_without_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, artifacts = _configure_private_publication(tmp_path, monkeypatch)
    collision = sources / publication.SOURCE_FILENAME
    real_promote = publication._promote_noreplace

    def collide(source: Path, destination: Path) -> None:
        if destination == collision and not collision.exists():
            collision.write_text("late collision", encoding="utf-8")
        real_promote(source, destination)

    monkeypatch.setattr(publication, "_promote_noreplace", collide)
    with pytest.raises(publication.EdgeConneXPublicationError):
        publication.build(recorded_at=_future(3), publication_authorized=True)
    assert collision.read_text(encoding="utf-8") == "late collision"
    assert not publication.ARTIFACT.exists()
    assert not list(artifacts.iterdir())
    assert not publication.PUBLICATION_LOCK.exists()
    assert list(sources.iterdir()) == [collision]


def test_reviewed_source_tamper_fails_without_touching_retained_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    retained = publication.REVIEWED_SOURCE_STAGE
    copied = tmp_path / "reviewed-sources"
    shutil.copytree(retained, copied)
    copied.chmod(0o700)
    for path in copied.iterdir():
        path.chmod(0o600)
    target = copied / publication.SOURCE_FILENAME
    target.write_bytes(target.read_bytes() + b"\n")
    monkeypatch.setattr(publication, "REVIEWED_SOURCE_STAGE", copied)
    with pytest.raises(
        publication.EdgeConneXPublicationError, match="pinned input differs"
    ):
        publication._validate_reviewed_inputs()
    publication._pin(
        retained / publication.SOURCE_FILENAME,
        publication.REVIEWED_SOURCE_PINS[publication.SOURCE_FILENAME],
        mode=0o600,
    )


def test_reviewed_artifact_tamper_fails_without_touching_retained_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    retained = publication.REVIEWED_ARTIFACT_STAGE
    copied = tmp_path / "reviewed-artifact"
    shutil.copytree(retained, copied)
    copied.chmod(0o700)
    for path in copied.iterdir():
        path.chmod(0o600)
    target = copied / "manifest.json"
    target.write_bytes(target.read_bytes() + b"\n")
    monkeypatch.setattr(publication, "REVIEWED_ARTIFACT_STAGE", copied)
    with pytest.raises(
        publication.EdgeConneXPublicationError, match="pinned input differs"
    ):
        publication._validate_reviewed_inputs()
    publication._pin(
        retained / "manifest.json",
        publication.REVIEWED_ARTIFACT_PINS["manifest.json"],
        mode=0o600,
    )


def test_resolvable_capture_clone_tamper_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    copied = tmp_path / "capture-clone"
    copied.mkdir(mode=0o700)
    for name in publication.RAW_CAPTURE_PINS:
        destination = copied / name
        destination.write_bytes(b"")
        destination.chmod(0o444)
    copied.chmod(0o555)
    monkeypatch.setattr(publication, "_resolve_raw_capture", lambda: copied)
    with pytest.raises(
        publication.EdgeConneXPublicationError, match="pinned input differs"
    ):
        publication._validate_reviewed_inputs()


def test_absent_capture_clone_uses_exact_reviewed_and_final_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(publication, "_resolve_raw_capture", lambda: None)
    identities = publication._validate_reviewed_inputs()
    assert identities.capture_path is None
    assert publication.validate_published()["capture_clone_retained"] is False


def test_stage_time_lock_and_identity_cleanup_guards_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stage = tmp_path / "stage"
    nested = stage / "nested"
    nested.mkdir(parents=True)
    payload = nested / "payload"
    payload.write_text("x", encoding="utf-8")
    with pytest.raises(
        publication.EdgeConneXPublicationError, match="post-dates recorded_at"
    ):
        publication._assert_stage_precedes(
            stage, datetime.now(UTC) - timedelta(seconds=10)
        )

    identities = publication._tree_identities(stage)
    replacement = nested / "payload.replacement"
    replacement.write_text("y", encoding="utf-8")
    payload.unlink()
    replacement.rename(payload)
    with pytest.raises(
        publication.EdgeConneXPublicationError,
        match="identity-mismatched stage cleanup",
    ):
        publication._discard_owned_tree(stage, expected=identities)

    lock = tmp_path / ".publication-lock"
    monkeypatch.setattr(publication, "PUBLICATION_LOCK", lock)
    with pytest.raises(
        publication.EdgeConneXPublicationError, match="substituted.*lock cleanup"
    ):
        with publication._publication_lock():
            lock.unlink()
            lock.write_text("replacement", encoding="utf-8")
    assert lock.read_text(encoding="utf-8") == "replacement"


def test_preflight_preserves_recursive_reviewed_input_identities(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_private_publication(tmp_path, monkeypatch)
    before = publication._validate_reviewed_inputs()
    publication.preflight(recorded_at="2099-01-01T00:00:00Z")
    publication._assert_reviewed_input_identities(before)
    assert not publication.ARTIFACT.exists()
    assert not publication._final_source().exists()
