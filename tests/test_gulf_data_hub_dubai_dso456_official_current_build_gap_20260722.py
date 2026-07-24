from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import stat

import pytest

try:
    from datacenter_atlas.datacenter_atlas import (
        gulf_data_hub_dubai_dso456_official_current_build_gap_20260722 as gap,
    )
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import (  # type: ignore[no-redef]
        gulf_data_hub_dubai_dso456_official_current_build_gap_20260722 as gap,
    )


def _future_timestamp(minutes: int = 10) -> str:
    return (
        (datetime.now(UTC).replace(microsecond=0) + timedelta(minutes=minutes))
        .isoformat()
        .replace("+00:00", "Z")
    )


def _stage(tmp_path: Path, recorded_at: str) -> tuple[Path, Path]:
    source_root = tmp_path / "sources"
    artifact_root = tmp_path / "artifact"
    source_root.mkdir(mode=0o700)
    artifact_root.mkdir(mode=0o700)
    documents = gap.expected_source_documents()
    paths = gap._write_sources(source_root, documents)
    records = gap._validate_sources(paths, frozen=False)
    payloads = gap._artifact_payloads(recorded_at, records, gap._collision_witness())
    gap._write_artifact(artifact_root, payloads, recorded_at)
    return source_root, artifact_root


def _configure_private_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    sources = tmp_path / "sources"
    artifacts = tmp_path / "source_artifacts"
    sources.mkdir()
    artifacts.mkdir()
    monkeypatch.setattr(gap, "SOURCES_ROOT", sources)
    monkeypatch.setattr(gap, "ARTIFACT_ROOT", artifacts)
    monkeypatch.setattr(gap, "ARTIFACT", artifacts / gap.ARTIFACT_ID)
    monkeypatch.setattr(gap, "PUBLICATION_LOCK", tmp_path / ".gdh.lock")
    return sources, artifacts


def _future_seconds(seconds: int = 2) -> str:
    return (
        (datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=seconds))
        .isoformat()
        .replace("+00:00", "Z")
    )


def test_exact_frozen_private_capture_and_official_wording() -> None:
    capture = gap.validate_private_capture()
    assert gap.CAPTURE_FILE_COUNT == 3
    assert sum(pin[0] for pin in gap.CAPTURE_FILE_PINS.values()) == 80_499
    assert gap.tree_digest(gap.CAPTURE_ROOT) == gap.CAPTURE_TREE_SHA256
    assert stat.S_IMODE(gap.CAPTURE_ROOT.stat().st_mode) == 0o555
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o444
        for path in gap.CAPTURE_ROOT.iterdir()
    )
    assert gap.STATUS_WORDING in capture["rendered_text"]
    assert gap.CAPACITY_WORDING in capture["rendered_text"]
    assert capture["writeout"] == {
        "http_code": 200,
        "url_effective": "https://www.gulfdatahub.ae/dubai",
        "content_type": "text/html; charset=utf-8",
        "remote_ip": "13.207.136.21",
        "ssl_verify_result": 0,
        "num_redirects": 0,
        "size_download": 8178,
        "time_total": 1.102911,
    }
    inventory = gap._retrieval_inventory(_future_timestamp())
    assert inventory["successful_http_200_body_captures"] == 1
    assert inventory["normalized_source_record_count"] == 3
    assert inventory["capture_retry_count"] == 0
    assert inventory["raw_capture_redistributed"] is False


def test_v95_and_current_artifacts_have_no_identity_or_alias_collision() -> None:
    witness = gap._collision_witness()
    assert witness["accepted_base_release_id"] == "2026-07-22-open-seed-v95"
    assert witness["accepted_base_entities"] == 1_029
    assert witness["accepted_base_tree_sha256"] == gap.V95_TREE_SHA256
    assert witness["current_source_documents_scanned"] > 0
    assert witness["stable_key_collision_count"] == 0
    assert witness["evidence_key_collision_count"] == 0
    assert witness["alias_collision_count"] == 0
    assert witness["alias_search_terms"] == list(gap.COLLISION_ALIASES)


def test_three_source_records_are_minimal_and_source_scoped() -> None:
    documents = gap.expected_source_documents()
    assert tuple(documents) == gap.SOURCE_FILENAMES
    assert len(documents) == 3
    assert {
        document["campus"]["stable_key"] for document in documents.values()
    } == gap.CAMPUS_KEYS
    assert {
        document["project"]["stable_key"] for document in documents.values()
    } == gap.PROJECT_KEYS
    assert {
        row["key"] for document in documents.values() for row in document["evidence"]
    } == gap.EVIDENCE_KEYS
    for document in documents.values():
        assert document["schema_version"] == "1.1"
        assert document["lifecycle"] == [
            {
                "entity": "project",
                "value": "under_construction",
                "evidence_key": document["evidence"][0]["key"],
                "as_of_date": "2026-07-22",
                "method": "authoritative_physical_status_update",
                "confidence": 0.99,
            }
        ]
        assert document["operating_models"] == []
        assert document["workloads"] == []
        assert document["capacities"] == []
        for entity in ("campus", "project"):
            assert document[entity]["country"] == "United Arab Emirates"
            assert document[entity]["address"] == "Dubai, United Arab Emirates"
            assert document[entity]["roles"] == {}
            assert document[entity]["coordinates"] is None
            assert document[entity]["geometry"] is None
        evidence = document["evidence"][0]
        assert evidence["source_url"] == gap.SOURCE_URL
        assert evidence["published_at"] is None
        assert evidence["retrieved_at"] == gap.RETRIEVED_AT
        assert evidence["metadata"]["official_status_wording"] == gap.STATUS_WORDING
        assert evidence["metadata"]["official_capacity_wording"] == (
            gap.CAPACITY_WORDING
        )
        assert "no capacity row" in evidence["metadata"]["capacity_exclusion"]
        assert "later persistence" in evidence["metadata"]["status_semantics"]


def test_prepublication_artifact_freezes_and_replays_exactly(
    tmp_path: Path,
) -> None:
    recorded_at = _future_timestamp()
    source_root, artifact_root = _stage(tmp_path, recorded_at)
    mutable = gap.validate_prepublication_artifact(
        source_root,
        artifact_root,
        recorded_at=recorded_at,
        require_frozen=False,
    )
    assert mutable["database_counts"] == {
        "entities": 6,
        "entity_snapshots": 6,
        "evidence": 3,
        "lifecycle_observations": 3,
        "operating_model_observations": 0,
        "workload_observations": 0,
        "capacity_estimates": 0,
    }
    gap._freeze_tree(source_root)
    gap._freeze_tree(artifact_root)
    try:
        frozen = gap.validate_prepublication_artifact(
            source_root,
            artifact_root,
            recorded_at=recorded_at,
            require_frozen=True,
        )
        manifest = frozen["manifest"]
        assert manifest["format"] == (
            "datacenter-atlas-official-source-artifact-manifest-v3"
        )
        assert manifest["candidate_assessments"] == 3
        assert manifest["curated_source_records"] == 3
        assert manifest["seed_eligible_candidates"] == 3
        assert manifest["capacity_estimates"] == 0
        assert manifest["accepted"] is False
        assert manifest["published"] is False
        snapshot = json.loads((artifact_root / "source-snapshot.json").read_text())
        assert snapshot["totals"]["distinct_entity_snapshots"] == 6
        assert snapshot["totals"]["computer_vision_observations"] == 0
        assert snapshot["claim_boundary"]["current_status_after_retrieval"] == (
            "unknown"
        )
        assert snapshot["integration"]["open_seed_successor_created"] is False
        assert stat.S_IMODE(source_root.stat().st_mode) == 0o555
        assert stat.S_IMODE(artifact_root.stat().st_mode) == 0o555
    finally:
        gap._thaw_tree(tmp_path)


def test_preflight_is_deterministic_discards_stage_and_leaves_finals_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_private_publication(tmp_path, monkeypatch)
    recorded_at = _future_timestamp()
    before = set(Path("/private/tmp").glob("gdh-dubai-dso456-prepublication-*"))
    first = gap.prepare_gdh_dubai_dso456(recorded_at=recorded_at)
    second = gap.prepare_gdh_dubai_dso456(recorded_at=recorded_at)
    after = set(Path("/private/tmp").glob("gdh-dubai-dso456-prepublication-*"))
    assert first == second
    assert first["status"] == "PREFLIGHT_VALIDATED_AND_DISCARDED"
    assert first["source_stage_discarded"] is True
    assert first["artifact_stage_discarded"] is True
    assert first["published"] is False
    assert first["accepted"] is False
    assert [row["sha256"] for row in first["source_pins"]] == [
        "64cddc09bdec92bd4ff2b17679452d13ebb607e4f1804ac80e8ad549a5d67c97",
        "5c7247bd51fa7fd7b4e338d9ff6a6c6e7c4bfa39f2bb8d9fff45d73302b8e440",
        "ac517277fcc182bc1dee02f9d000e7fdfa381aa3471b3e7c6eaa01690b6ea006",
    ]
    assert before == after
    assert not gap.ARTIFACT.exists()
    assert not gap.PUBLICATION_LOCK.exists()
    assert not any((gap.SOURCES_ROOT / name).exists() for name in gap.SOURCE_FILENAMES)


def test_source_and_artifact_tampering_fail_closed(tmp_path: Path) -> None:
    recorded_at = _future_timestamp()
    source_root, artifact_root = _stage(tmp_path, recorded_at)
    source = source_root / gap.SOURCE_FILENAMES[0]
    source.write_bytes(source.read_bytes() + b"\n")
    with pytest.raises(gap.GulfDataHubDubaiGapError, match="source"):
        gap.validate_prepublication_artifact(
            source_root,
            artifact_root,
            recorded_at=recorded_at,
            require_frozen=False,
        )
    source.write_bytes(
        gap._canonical(gap.expected_source_documents()[gap.SOURCE_FILENAMES[0]])
    )
    assessment = artifact_root / "candidate-assessment.json"
    assessment.write_bytes(assessment.read_bytes() + b" ")
    with pytest.raises(gap.GulfDataHubDubaiGapError, match="manifest pin"):
        gap.validate_prepublication_artifact(
            source_root,
            artifact_root,
            recorded_at=recorded_at,
            require_frozen=False,
        )


def test_accepted_payloads_publish_only_minimal_source_scoped_claims(
    tmp_path: Path,
) -> None:
    recorded_at = _future_timestamp()
    source_root = tmp_path / "sources"
    source_root.mkdir()
    source_paths = gap._write_sources(source_root, gap.expected_source_documents())
    source_records = gap._validate_sources(source_paths, frozen=False)
    payloads = gap._accepted_artifact_payloads(
        recorded_at, source_records, gap._collision_witness()
    )
    manifest = gap._accepted_artifact_manifest(recorded_at, payloads)
    snapshot = json.loads(payloads["source-snapshot.json"])
    assessment = json.loads(payloads["candidate-assessment.json"])
    inventory = json.loads(payloads["retrieval-inventory.json"])
    rights = json.loads(payloads["rights-and-disposition.json"])
    assert manifest["accepted"] is True
    assert manifest["published"] is True
    assert manifest["publication_status"] == "accepted"
    assert manifest["capacity_estimates"] == 0
    assert snapshot["integration"]["published"] is True
    assert snapshot["integration"]["open_seed_successor_created"] is False
    assert snapshot["totals"]["capacity_estimates"] == 0
    assert all(row["accepted"] is True for row in snapshot["source_records"])
    assert all(row["published"] is True for row in assessment["candidates"])
    assert "capture_directory" not in inventory
    assert inventory["capture_storage_path_redacted"] is True
    assert "private_capture_directory" not in rights
    assert rights["private_capture_storage_path_redacted"] is True
    for raw in payloads.values():
        assert "prepublication" not in raw.decode("utf-8").lower()


def test_publication_requires_explicit_authorization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_private_publication(tmp_path, monkeypatch)
    with pytest.raises(
        gap.GulfDataHubDubaiGapError, match="publication_authorized=True"
    ):
        gap.publish_gdh_dubai_dso456()
    assert not gap.ARTIFACT.exists()
    assert not gap.PUBLICATION_LOCK.exists()
    assert not any((gap.SOURCES_ROOT / name).exists() for name in gap.SOURCE_FILENAMES)


def test_accepted_format_preflight_is_frozen_and_fully_discarded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_private_publication(tmp_path, monkeypatch)
    result = gap.preflight_gdh_dubai_dso456_publication(recorded_at=_future_timestamp())
    assert result["status"] == ("ACCEPTED_FORMAT_PREFLIGHT_VALIDATED_AND_DISCARDED")
    assert result["accepted_format"] is True
    assert result["published"] is False
    assert result["source_stage_discarded"] is True
    assert result["artifact_stage_discarded"] is True
    assert result["database_counts"]["entities"] == 6
    assert not gap.ARTIFACT.exists()
    assert not gap.PUBLICATION_LOCK.exists()


def test_private_authorized_publication_and_existing_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, _artifacts = _configure_private_publication(tmp_path, monkeypatch)
    recorded_at = _future_seconds(2)
    try:
        first = gap.publish_gdh_dubai_dso456(
            recorded_at=recorded_at, publication_authorized=True
        )
        assert first["status"] == "published"
        assert first["published"] is True
        assert gap.ARTIFACT.is_dir()
        assert stat.S_IMODE(gap.ARTIFACT.stat().st_mode) == 0o555
        assert all(
            stat.S_IMODE((sources / name).stat().st_mode) == 0o444
            for name in gap.SOURCE_FILENAMES
        )
        assert not gap.PUBLICATION_LOCK.exists()
        assert not list(sources.glob(".gdh-dubai-dso456-source-stage-*"))
        second = gap.publish_gdh_dubai_dso456(
            recorded_at=recorded_at, publication_authorized=True
        )
        assert second["status"] == "existing-identical"
        assert second["manifest_sha256"] == first["manifest_sha256"]
        assert second["artifact_tree_sha256"] == first["artifact_tree_sha256"]
    finally:
        gap._thaw_tree(tmp_path)


def test_authorized_publication_rolls_back_on_artifact_promotion_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, artifacts = _configure_private_publication(tmp_path, monkeypatch)
    real_promote = gap._promote_noreplace

    def fail_artifact(source: Path, destination: Path) -> None:
        if destination == gap.ARTIFACT:
            raise gap.GulfDataHubDubaiGapError("injected artifact failure")
        real_promote(source, destination)

    monkeypatch.setattr(gap, "_promote_noreplace", fail_artifact)
    with pytest.raises(gap.GulfDataHubDubaiGapError, match="injected artifact"):
        gap.publish_gdh_dubai_dso456(
            recorded_at=_future_seconds(2), publication_authorized=True
        )
    assert not gap.ARTIFACT.exists()
    assert not any((sources / name).exists() for name in gap.SOURCE_FILENAMES)
    assert not gap.PUBLICATION_LOCK.exists()
    assert not list(sources.iterdir())
    assert not list(artifacts.iterdir())


def test_partial_final_collision_fails_before_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, artifacts = _configure_private_publication(tmp_path, monkeypatch)
    (sources / gap.SOURCE_FILENAMES[0]).write_text("collision")
    with pytest.raises(gap.GulfDataHubDubaiGapError, match="partial final-path"):
        gap.publish_gdh_dubai_dso456(
            recorded_at=_future_timestamp(), publication_authorized=True
        )
    assert len(list(sources.iterdir())) == 1
    assert not list(artifacts.iterdir())
    assert not gap.PUBLICATION_LOCK.exists()


def test_publication_lock_identity_guard_refuses_substitution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = tmp_path / ".lock"
    monkeypatch.setattr(gap, "PUBLICATION_LOCK", lock)
    with pytest.raises(gap.GulfDataHubDubaiGapError, match="substituted.*lock cleanup"):
        with gap._publication_lock():
            lock.unlink()
            lock.write_text("replacement")
    assert lock.read_text() == "replacement"
