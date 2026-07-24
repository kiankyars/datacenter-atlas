from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import shutil
import stat

import pytest

try:
    from datacenter_atlas.datacenter_atlas import (
        official_nxdata3_current_build_20260722 as publication,
    )
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import (  # type: ignore[no-redef]
        official_nxdata3_current_build_20260722 as publication,
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


def test_reviewed_lineage_raw_capture_and_predecessor_are_exact() -> None:
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
    assert stat.S_IMODE(publication.RAW_CAPTURE.stat().st_mode) == 0o555
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o444
        for path in publication.RAW_CAPTURE.iterdir()
    )
    assert set(publication.REVIEWED_SOURCE_PINS) == {publication.SOURCE_FILENAME}
    assert len(publication.REVIEWED_ARTIFACT_PINS) == 7
    assert len(publication.RAW_CAPTURE_PINS) == 26
    publication._pin(
        publication.PREDECESSOR,
        publication.PREDECESSOR_PIN,
        mode=publication.PREDECESSOR_MODE,
    )
    publication._assert_reviewed_input_identities(identities)


def test_accepted_source_is_distinct_and_preserves_guarded_semantics() -> None:
    document = publication.expected_source_document()
    raw = publication._canonical(document)
    assert (len(raw), publication._sha256_bytes(raw)) == (
        13_866,
        "1ed2d1999113ac32def96a319d5283865ef6f2cd9e37db1a4c2d5cbda03d3ab3",
    )
    assert (len(raw), publication._sha256_bytes(raw)) != (
        publication.REVIEWED_SOURCE_PINS[publication.SOURCE_FILENAME]
    )
    assert publication.ARTIFACT_ID in raw.decode("utf-8")
    assert publication.REVIEWED_CANDIDATE_ID not in raw.decode("utf-8")
    assert document["campus"]["stable_key"] == publication.CAMPUS_KEY
    assert document["project"]["stable_key"] == publication.PROJECT_KEY
    assert document["lifecycle"] == [
        {
            "as_of_date": "2026-06-02",
            "confidence": 0.99,
            "entity": "project",
            "evidence_key": (
                "nxdata3-official-foundation-progress-2026-06-02-captured-2026-07-22"
            ),
            "method": "authoritative_physical_status_update",
            "value": "under_construction",
        }
    ]
    assert document["operating_models"][0]["value"] == "colocation"
    assert [
        (row["metric"], row["stage"], row["base"], row["unit"])
        for row in document["capacities"]
    ] == [
        ("gross_facility_mw", "design", 5, "MW"),
        ("critical_it_mw", "design", 3, "MW"),
        ("pue", "design", 1.3, "ratio"),
    ]
    assert document["workloads"] == []
    for entity in ("campus", "project"):
        assert document[entity]["coordinates"] is None
        assert document[entity]["geometry"] is None


def test_artifact_accepts_only_nxdata_and_keeps_other_leads_review_only() -> None:
    recorded_at = "2099-01-01T00:00:00Z"
    payloads = publication._artifact_documents(
        recorded_at, publication.expected_source_document()
    )
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
    assert len(snapshot["source_records"]) == 1
    source_record = snapshot["source_records"][0]
    assert source_record["path"] == f"sources/{publication.SOURCE_FILENAME}"
    assert source_record["accepted"] is True
    assert source_record["published"] is True
    assert source_record["seeded"] is False
    assert assessment["accepted_source_record_count"] == 1
    assert assessment["review_only_count"] == 3
    accepted = [row for row in assessment["candidates"] if row["accepted"]]
    assert [row["candidate_id"] for row in accepted] == ["nxdata3-buh3"]
    for candidate_id in (
        "porr-anonymous-eighth-february-2025",
        "porr-waw-11-1",
        "data4-jawczyce-second-data-center",
    ):
        row = next(
            item
            for item in assessment["candidates"]
            if item["candidate_id"] == candidate_id
        )
        assert row["source_paths"] == []
        assert row["accepted"] is False
        assert row["published"] is False
        assert row["seeded"] is False


def test_predecessor_replacement_is_explicit_and_non_mutating() -> None:
    before = (
        publication._identity(publication.PREDECESSOR, directory=False),
        publication.PREDECESSOR.read_bytes(),
    )
    document = publication.expected_source_document()
    record = publication._source_record(document)
    contract = publication._replacement_contract()
    assert (
        record["replaces_source_path"] == f"sources/{publication.PREDECESSOR_FILENAME}"
    )
    assert record["replacement_semantics"] == (
        "successor_supersedes_predecessor_for_future_source_selection"
    )
    assert contract["predecessor_retained_immutable"] is True
    assert contract["predecessor_modified"] is False
    assert contract["predecessor_deleted"] is False
    assert contract["select_predecessor_and_successor_together"] is False
    assert contract["successor_reuses_exact_stable_keys"] == [
        publication.CAMPUS_KEY,
        publication.PROJECT_KEY,
    ]
    after = (
        publication._identity(publication.PREDECESSOR, directory=False),
        publication.PREDECESSOR.read_bytes(),
    )
    assert after == before


def test_all_accepted_bytes_redact_private_and_candidate_paths() -> None:
    document = publication.expected_source_document()
    payloads = publication._artifact_documents("2099-01-01T00:00:00Z", document)
    all_payloads = [publication._canonical(document), *payloads.values()]
    for payload in all_payloads:
        lowered = payload.decode("utf-8").lower()
        assert str(publication.RAW_CAPTURE).lower() not in lowered
        assert "/private/tmp/" not in lowered
        assert "prospective-sources/" not in lowered
        assert "prepublication" not in lowered
    inventory = json.loads(payloads["retrieval-inventory.json"])
    rights = json.loads(payloads["rights-and-disposition.json"])
    lineage = json.loads(payloads["source-snapshot.json"])["reviewed_candidate_lineage"]
    assert "capture_directory" not in inventory
    assert "private_capture_directory" not in rights
    assert inventory["raw_capture_storage_path_redacted"] is True
    assert rights["raw_capture_storage_path_redacted"] is True
    assert lineage["raw_capture_storage_path_redacted"] is True
    assert lineage["raw_capture_tree_sha256"] == publication.RAW_CAPTURE_TREE_SHA256


def test_default_authorization_fails_closed_and_changes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_private_publication(tmp_path, monkeypatch)
    assert not publication.ARTIFACT.exists()
    assert not publication._final_source().exists()
    before = (
        publication._identity(publication.REVIEWED_SOURCE_STAGE, directory=True),
        publication._identity(publication.REVIEWED_ARTIFACT_STAGE, directory=True),
        publication._identity(publication.RAW_CAPTURE, directory=True),
        publication._identity(publication.PREDECESSOR, directory=False),
    )
    with pytest.raises(
        publication.NXDataPublicationError,
        match="publication_authorized=True",
    ):
        publication.build()
    after = (
        publication._identity(publication.REVIEWED_SOURCE_STAGE, directory=True),
        publication._identity(publication.REVIEWED_ARTIFACT_STAGE, directory=True),
        publication._identity(publication.RAW_CAPTURE, directory=True),
        publication._identity(publication.PREDECESSOR, directory=False),
    )
    assert after == before
    assert not publication.ARTIFACT.exists()
    assert not publication._final_source().exists()


def test_preflight_is_deterministic_frozen_and_fully_discarded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_private_publication(tmp_path, monkeypatch)
    recorded_at = "2099-01-01T00:00:00Z"
    first = publication.preflight(recorded_at=recorded_at)
    second = publication.preflight(recorded_at=recorded_at)
    for key in (
        "artifact_manifest_sha256",
        "artifact_tree_sha256",
        "artifact_pins",
        "source_tree_sha256",
        "source_pins",
        "predecessor_pin",
        "modes",
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
    assert first["raw_capture_storage_path_redacted"] is True
    assert first["predecessor_retained"] is True
    assert not publication.ARTIFACT.exists()
    assert not publication._final_source().exists()


def test_prepare_uses_unique_same_filesystem_stages_and_recursive_chronology(
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
        assert set(first.artifact_identities) == {
            ".",
            *publication.CLOSED_FILES,
        }
    finally:
        publication._discard_owned_tree(
            first.source_stage, expected=first.source_identities
        )
        publication._discard_owned_tree(
            first.artifact_stage, expected=first.artifact_identities
        )
        publication._discard_owned_tree(
            second.source_stage, expected=second.source_identities
        )
        publication._discard_owned_tree(
            second.artifact_stage, expected=second.artifact_identities
        )


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


def test_authorized_private_publication_and_existing_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, _artifacts = _configure_private_publication(tmp_path, monkeypatch)
    recorded_at = _future(2)
    first = publication.build(recorded_at=recorded_at, publication_authorized=True)
    assert first["status"] == "published"
    assert first["published"] is True
    assert publication.ARTIFACT.is_dir()
    assert (sources / publication.SOURCE_FILENAME).is_file()
    assert stat.S_IMODE(publication.ARTIFACT.stat().st_mode) == 0o555
    assert stat.S_IMODE((sources / publication.SOURCE_FILENAME).stat().st_mode) == 0o444
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o444
        for path in publication.ARTIFACT.iterdir()
    )
    assert not publication.PUBLICATION_LOCK.exists()
    assert not list(sources.glob(".official-nxdata3-current-build-source-stage-*"))
    second = publication.build(recorded_at=recorded_at, publication_authorized=True)
    assert second["status"] == "existing-identical"
    assert second["manifest_sha256"] == first["manifest_sha256"]
    assert second["artifact_tree_sha256"] == first["artifact_tree_sha256"]


def test_artifact_failure_rolls_back_source_and_discards_stages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, artifacts = _configure_private_publication(tmp_path, monkeypatch)
    real_promote = publication._promote_noreplace

    def fail_artifact(source: Path, destination: Path) -> None:
        if destination == publication.ARTIFACT:
            raise publication.NXDataPublicationError("injected artifact failure")
        real_promote(source, destination)

    monkeypatch.setattr(publication, "_promote_noreplace", fail_artifact)
    with pytest.raises(
        publication.NXDataPublicationError, match="injected artifact failure"
    ):
        publication.build(recorded_at=_future(2), publication_authorized=True)
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
        publication.NXDataPublicationError, match="partial final-path collision"
    ):
        publication.build(recorded_at=_future(30), publication_authorized=True)
    assert list(sources.iterdir()) == [collision]
    assert not list(artifacts.iterdir())
    assert not publication.PUBLICATION_LOCK.exists()


def test_no_replace_collision_after_staging_fails_without_overwrite(
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
    with pytest.raises(publication.NXDataPublicationError):
        publication.build(recorded_at=_future(2), publication_authorized=True)
    assert collision.read_text(encoding="utf-8") == "late collision"
    assert not publication.ARTIFACT.exists()
    assert not list(artifacts.iterdir())
    assert not publication.PUBLICATION_LOCK.exists()
    assert list(sources.iterdir()) == [collision]


def test_reviewed_source_tamper_fails_closed_without_touching_real_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_stage = publication.REVIEWED_SOURCE_STAGE
    copied = tmp_path / "reviewed-sources"
    shutil.copytree(real_stage, copied)
    copied.chmod(0o700)
    for path in copied.iterdir():
        path.chmod(0o600)
    target = copied / publication.SOURCE_FILENAME
    target.write_bytes(target.read_bytes() + b"\n")
    monkeypatch.setattr(publication, "REVIEWED_SOURCE_STAGE", copied)
    with pytest.raises(
        publication.NXDataPublicationError, match="pinned input differs"
    ):
        publication._validate_reviewed_inputs()
    publication._pin(
        real_stage / publication.SOURCE_FILENAME,
        publication.REVIEWED_SOURCE_PINS[publication.SOURCE_FILENAME],
        mode=0o600,
    )


def test_predecessor_tamper_fails_closed_and_real_predecessor_is_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    copied = tmp_path / publication.PREDECESSOR_FILENAME
    shutil.copy2(publication.PREDECESSOR, copied)
    copied.chmod(0o644)
    copied.write_bytes(copied.read_bytes() + b"\n")
    monkeypatch.setattr(publication, "PREDECESSOR", copied)
    with pytest.raises(
        publication.NXDataPublicationError, match="pinned input differs"
    ):
        publication._validate_reviewed_inputs()
    monkeypatch.undo()
    publication._pin(
        publication.PREDECESSOR,
        publication.PREDECESSOR_PIN,
        mode=publication.PREDECESSOR_MODE,
    )


def test_raw_capture_inventory_tamper_fails_before_rendering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    copied = tmp_path / "raw-captures"
    copied.mkdir(mode=0o700)
    unexpected = copied / "unexpected.body"
    unexpected.write_bytes(b"x")
    unexpected.chmod(0o444)
    copied.chmod(0o555)
    monkeypatch.setattr(publication, "RAW_CAPTURE", copied)
    with pytest.raises(
        publication.NXDataPublicationError, match="raw capture bundle inventory differs"
    ):
        publication._validate_reviewed_inputs()


def test_stage_time_lock_and_identity_cleanup_guards_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stage = tmp_path / "stage"
    nested = stage / "nested"
    nested.mkdir(parents=True)
    payload = nested / "payload"
    payload.write_text("x", encoding="utf-8")
    target = datetime.now(UTC) - timedelta(seconds=10)
    with pytest.raises(
        publication.NXDataPublicationError, match="post-dates recorded_at"
    ):
        publication._assert_stage_precedes(stage, target)

    identities = publication._tree_identities(stage)
    replacement = nested / "payload.replacement"
    replacement.write_text("y", encoding="utf-8")
    payload.unlink()
    replacement.rename(payload)
    with pytest.raises(
        publication.NXDataPublicationError,
        match="identity-mismatched stage cleanup",
    ):
        publication._discard_owned_tree(stage, expected=identities)

    lock = tmp_path / ".publication-lock"
    monkeypatch.setattr(publication, "PUBLICATION_LOCK", lock)
    with pytest.raises(
        publication.NXDataPublicationError, match="substituted.*lock cleanup"
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
