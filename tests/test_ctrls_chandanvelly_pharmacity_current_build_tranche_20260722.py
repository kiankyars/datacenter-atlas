from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import shutil
import socket
import stat

import pytest

try:
    from datacenter_atlas.datacenter_atlas import (
        ctrls_chandanvelly_pharmacity_current_build_tranche_20260722 as publication,
    )
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import (  # type: ignore[no-redef]
        ctrls_chandanvelly_pharmacity_current_build_tranche_20260722 as publication,
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
    tmp_path.mkdir(parents=True, exist_ok=True)
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
    assert publication.REVIEWED_RECORDED_AT == "2026-07-22T04:58:20Z"
    assert publication.REVIEWED_SOURCE_TREE_SHA256 == (
        "152b7c5f1941043cc048f04a441b50c6eb4356bd31d28f5fa9fef1dccf89343c"
    )
    assert publication.tree_digest(publication.REVIEWED_SOURCE_STAGE) == (
        publication.REVIEWED_SOURCE_TREE_SHA256
    )
    assert publication.REVIEWED_ARTIFACT_TREE_SHA256 == (
        "da8f9bff9a1f7becaf38b554fb52d587703cec4e6b9f1664c6560666c96694eb"
    )
    assert publication.tree_digest(publication.REVIEWED_ARTIFACT_STAGE) == (
        publication.REVIEWED_ARTIFACT_TREE_SHA256
    )
    assert publication.RAW_CAPTURE_TREE_SHA256 == (
        "702b3c5257c81b60d2d5b16df0cf9c41df826012018bbe72d5f79942255bbecc"
    )
    assert publication.tree_digest(publication._raw_capture()) == (
        publication.RAW_CAPTURE_TREE_SHA256
    )
    assert publication.REVIEWED_SOURCE_PINS == {
        publication.CHANDANVELLY_SOURCE_FILENAME: (
            7_825,
            "af57d566fde98ad81d52b89df6709bece2d6fa46a0f0e5302ae9df5e0ad40c37",
        ),
        publication.PHARMACITY_SOURCE_FILENAME: (
            4_932,
            "fc9175408fff782eaedce12d5da04b5125caa103dfe194f6032b26d1ff6b737b",
        ),
    }
    assert len(publication.REVIEWED_ARTIFACT_PINS) == 7
    assert publication.REVIEWED_ARTIFACT_PINS["manifest.json"] == (
        1_599,
        "0830dc2f1a400432fc502d7fa94387940d322c786e71273ed85fda7f1214c001",
    )
    assert len(publication.RAW_CAPTURE_PINS) == 30
    assert sum(pin[0] for pin in publication.RAW_CAPTURE_PINS.values()) == 3_431_628
    assert stat.S_IMODE(publication.REVIEWED_SOURCE_STAGE.stat().st_mode) == 0o700
    assert stat.S_IMODE(publication.REVIEWED_ARTIFACT_STAGE.stat().st_mode) == 0o700
    assert stat.S_IMODE(publication._raw_capture().stat().st_mode) == 0o555
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o444
        for path in publication._raw_capture().iterdir()
    )
    publication._assert_reviewed_input_identities(identities)


def test_final_source_payloads_are_byte_identical_and_claim_sparse() -> None:
    documents = publication.expected_source_documents()
    assert tuple(documents) == publication.SOURCE_FILENAMES
    assert sum(len(document["evidence"]) for document in documents.values()) == 3
    assert sum(len(document["lifecycle"]) for document in documents.values()) == 2
    for name, document in documents.items():
        reviewed = (publication.REVIEWED_SOURCE_STAGE / name).read_bytes()
        assert publication._canonical(document) == reviewed
        assert (len(reviewed), publication._sha256_bytes(reviewed)) == (
            publication.REVIEWED_SOURCE_PINS[name]
        )
        assert document["operating_models"] == []
        assert document["workloads"] == []
        assert document["capacities"] == []
        assert document["lifecycle"] == [
            {
                "entity": "project",
                "value": "under_construction",
                "evidence_key": document["lifecycle"][0]["evidence_key"],
                "as_of_date": "2026-07-21",
                "method": "authoritative_physical_status_update",
                "confidence": document["lifecycle"][0]["confidence"],
            }
        ]
        for entity in ("campus", "project"):
            assert document[entity]["roles"] == {"developer": ["CtrlS Datacenters Ltd"]}
            assert document[entity]["coordinates"] is None
            assert document[entity]["geometry"] is None

    chandan = documents[publication.CHANDANVELLY_SOURCE_FILENAME]
    assert (
        chandan["evidence"][0]["metadata"]["current_page_capacity_not_normalized"][
            "capacity_row_created"
        ]
        is False
    )
    assert chandan["evidence"][1]["metadata"]["announcement_only"] is True
    assert (
        chandan["evidence"][1]["metadata"]["lifecycle_claim_from_this_evidence"]
        is False
    )
    pharmacity = documents[publication.PHARMACITY_SOURCE_FILENAME]
    assert (
        pharmacity["evidence"][0]["metadata"]["capacity_not_normalized"][
            "capacity_row_created"
        ]
        is False
    )
    assert (
        pharmacity["evidence"][0]["metadata"]["green_power_not_normalized"][
            "energy_or_efficiency_row_created"
        ]
        is False
    )


def test_accepted_artifact_is_redacted_hash_lineage_with_ten_exclusions() -> None:
    recorded_at = "2026-07-22T06:00:00Z"
    payloads = publication._artifact_documents(
        recorded_at, publication.expected_source_documents()
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
    assert snapshot["totals"]["accepted_source_records"] == 2
    assert snapshot["totals"]["rejected_review_only_candidates"] == 10
    assert snapshot["totals"]["evidence_records"] == 3
    assert snapshot["totals"]["lifecycle_observations"] == 2
    assert snapshot["totals"]["capacity_estimates"] == 0
    assert snapshot["totals"]["energy_consumption_observations"] == 0
    assert snapshot["totals"]["coordinate_observations"] == 0
    assert all(
        row["path"].startswith("sources/")
        and row["accepted"] is True
        and row["published"] is True
        and (row["bytes"], row["sha256"])
        == publication.REVIEWED_SOURCE_PINS[Path(row["path"]).name]
        for row in snapshot["source_records"]
    )
    accepted = [row for row in assessment["candidates"] if row["accepted"]]
    rejected = [row for row in assessment["candidates"] if row["rejected"]]
    assert len(accepted) == 2
    assert len(rejected) == 10
    for row in rejected:
        assert row["source_paths"] == []
        assert row["published"] is False
        assert row["stable_key_created"] is False
        assert row["evidence_record_created"] is False
        assert row["lifecycle_claim_created"] is False
        assert row["capacity_claim_created"] is False
        assert row["energy_claim_created"] is False

    lineage = snapshot["reviewed_candidate_lineage"]
    assert lineage["purpose"] == "hash_only_reviewed_candidate_lineage"
    assert set(lineage["reviewed_source_file_pins"][0]) == {"bytes", "sha256"}
    assert len(lineage["reviewed_source_file_pins"]) == 2
    assert len(lineage["reviewed_artifact_file_pins"]) == 7
    assert len(lineage["raw_capture_file_pins"]) == 30
    assert lineage["reviewed_source_payloads_byte_identical"] is True
    assert lineage["reviewed_input_inodes_promoted"] is False
    assert "artifact_id" not in lineage
    assert "path" not in json.dumps(lineage).lower()

    banned = (
        "/users/",
        "/private/",
        "prepublication",
        "prospective-sources",
        str(publication.REVIEWED_SOURCE_STAGE).lower(),
        str(publication.REVIEWED_ARTIFACT_STAGE).lower(),
        str(publication.RAW_CAPTURE).lower(),
    )
    for raw in payloads.values():
        lowered = raw.decode("utf-8").lower()
        assert not any(token in lowered for token in banned)
    serialized = b"\n".join(payloads.values()).decode("utf-8")
    for key in (
        "prepublication_contract",
        "curated_source_candidates",
        "governed_prepublication_candidates",
        "prospective_final_artifact_exists",
        "prospective_final_source_exists",
    ):
        assert key not in serialized


def test_default_authorization_fails_without_final_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_private_publication(tmp_path, monkeypatch)
    with pytest.raises(
        publication.CtrlSPublicationError, match="publication_authorized=True"
    ):
        publication.build()
    assert not publication.ARTIFACT.exists()
    assert not any(path.exists() for path in publication._final_source_paths().values())


def test_preflight_is_offline_exactly_two_passes_deterministic_and_discarded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_private_publication(tmp_path, monkeypatch)
    recorded_at = _future(90)
    real_import = publication.CuratedOfficialSourceAdapterV11.import_file
    calls: list[str] = []

    def counted_import(
        self: object, connection: object, source: Path, **kwargs: object
    ):
        calls.append(source.name)
        return real_import(self, connection, source, **kwargs)

    def no_network(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("network access attempted")

    monkeypatch.setattr(
        publication.CuratedOfficialSourceAdapterV11, "import_file", counted_import
    )
    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket, "getaddrinfo", no_network)
    first = publication.preflight(recorded_at=recorded_at)
    assert calls == list(publication.SOURCE_FILENAMES) * 2
    calls.clear()
    second = publication.preflight(recorded_at=recorded_at)
    assert calls == list(publication.SOURCE_FILENAMES) * 2
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
    assert first["accepted_final_already_present"] is False
    assert first["source_stage_discarded"] is True
    assert first["artifact_stage_discarded"] is True
    assert first["reviewed_source_stage_retained"] is True
    assert first["reviewed_artifact_stage_retained"] is True
    assert first["raw_capture_retained"] is True
    assert first["final_artifact_exists"] is False
    assert first["final_source_exists"] is False
    assert first["rows"] == {
        "entity_snapshots": 4,
        "evidence": 3,
        "lifecycle": 2,
        "facility_types": 0,
        "operating_models": 0,
        "workloads": 0,
        "capacities": 0,
        "energy_consumption": 0,
        "coordinates": 0,
        "geometry": 0,
    }


def test_private_publication_existing_identical_and_postpublication_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, _artifacts = _configure_private_publication(tmp_path, monkeypatch)
    recorded_at = _future(2)
    first = publication.build(recorded_at=recorded_at, publication_authorized=True)
    assert first["status"] == "published"
    assert not publication.PUBLICATION_LOCK.exists()
    for name in publication.SOURCE_FILENAMES:
        final = sources / name
        assert (
            final.read_bytes()
            == (publication.REVIEWED_SOURCE_STAGE / name).read_bytes()
        )
        assert stat.S_IMODE(final.stat().st_mode) == 0o444
    assert stat.S_IMODE(publication.ARTIFACT.stat().st_mode) == 0o555
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o444
        for path in publication.ARTIFACT.iterdir()
    )
    target = publication._instant(recorded_at).timestamp()
    for path in (
        publication.ARTIFACT,
        *publication.ARTIFACT.rglob("*"),
        *publication._final_source_paths().values(),
    ):
        metadata = path.stat(follow_symlinks=False)
        birth = getattr(metadata, "st_birthtime", metadata.st_ctime)
        assert max(birth, metadata.st_mtime) <= target + 0.000_001
        assert metadata.st_ctime + 0.000_001 >= target

    second = publication.build(recorded_at=recorded_at, publication_authorized=True)
    assert second["status"] == "existing-identical"
    assert second["manifest_sha256"] == first["manifest_sha256"]
    before = publication.tree_digest(publication.ARTIFACT)
    check = publication.preflight(recorded_at=_future(60))
    assert check["accepted_final_already_present"] is True
    assert check["final_artifact_exists"] is True
    assert check["final_source_exists"] is True
    assert publication.tree_digest(publication.ARTIFACT) == before
    assert not list(sources.glob(".ctrls-chandanvelly-pharmacity-source-stage-*"))


def test_artifact_promotion_failure_rolls_back_all_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, artifacts = _configure_private_publication(tmp_path, monkeypatch)
    real_promote = publication._promote_noreplace

    def fail_artifact(source: Path, destination: Path) -> None:
        if destination == publication.ARTIFACT:
            raise publication.CtrlSPublicationError("injected artifact failure")
        real_promote(source, destination)

    monkeypatch.setattr(publication, "_promote_noreplace", fail_artifact)
    with pytest.raises(
        publication.CtrlSPublicationError, match="injected artifact failure"
    ):
        publication.build(recorded_at=_future(2), publication_authorized=True)
    assert not publication.ARTIFACT.exists()
    assert not any((sources / name).exists() for name in publication.SOURCE_FILENAMES)
    assert not publication.PUBLICATION_LOCK.exists()
    assert not list(sources.iterdir())
    assert not list(artifacts.iterdir())


def test_partial_and_semantic_collisions_fail_before_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, artifacts = _configure_private_publication(tmp_path, monkeypatch)
    partial = sources / publication.CHANDANVELLY_SOURCE_FILENAME
    partial.write_text("collision", encoding="utf-8")
    with pytest.raises(
        publication.CtrlSPublicationError, match="partial final-path collision"
    ):
        publication.preflight(recorded_at=_future(30))
    partial.unlink()
    later = {
        "campus": {
            "stable_key": "curated:other",
            "name": "Existing CtrlS Pharmacity campus",
            "address": "Hyderabad",
        },
        "project": {},
        "evidence": [],
    }
    (sources / "curated-later-source.json").write_text(
        json.dumps(later), encoding="utf-8"
    )
    with pytest.raises(publication.CtrlSPublicationError, match="later curated source"):
        publication.preflight(recorded_at=_future(30))
    assert not publication.ARTIFACT.exists()
    assert not list(artifacts.iterdir())


def test_reviewed_input_tamper_fails_without_touching_real_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_stage = publication.REVIEWED_SOURCE_STAGE
    copied = tmp_path / "reviewed-sources"
    shutil.copytree(real_stage, copied)
    copied.chmod(0o700)
    for path in copied.iterdir():
        path.chmod(0o600)
    target = copied / publication.CHANDANVELLY_SOURCE_FILENAME
    target.write_bytes(target.read_bytes() + b"\n")
    monkeypatch.setattr(publication, "REVIEWED_SOURCE_STAGE", copied)
    with pytest.raises(publication.CtrlSPublicationError, match="pinned input differs"):
        publication._validate_reviewed_inputs()
    publication._pin(
        real_stage / publication.CHANDANVELLY_SOURCE_FILENAME,
        publication.REVIEWED_SOURCE_PINS[publication.CHANDANVELLY_SOURCE_FILENAME],
        mode=0o600,
    )


def test_lock_substitution_and_initialization_failures_clean_safely(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = tmp_path / ".publication-lock"
    monkeypatch.setattr(publication, "PUBLICATION_LOCK", lock)
    with pytest.raises(
        publication.CtrlSPublicationError, match="substituted.*lock cleanup"
    ):
        with publication._publication_lock():
            lock.unlink()
            lock.write_text("replacement", encoding="utf-8")
    assert lock.read_text(encoding="utf-8") == "replacement"
    lock.unlink()

    with monkeypatch.context() as scoped:
        scoped.setattr(publication, "PUBLICATION_LOCK", lock)

        def fail_write(*_args: object, **_kwargs: object) -> int:
            raise OSError("injected write failure")

        scoped.setattr(publication.os, "write", fail_write)
        with pytest.raises(OSError, match="injected write failure"):
            with publication._publication_lock():
                pass
        assert not lock.exists()

    with monkeypatch.context() as scoped:
        scoped.setattr(publication, "PUBLICATION_LOCK", lock)
        real_fsync = publication.os.fsync

        def fail_fsync(descriptor: int) -> None:
            if lock.exists():
                raise OSError("injected fsync failure")
            real_fsync(descriptor)

        scoped.setattr(publication.os, "fsync", fail_fsync)
        with pytest.raises(OSError, match="injected fsync failure"):
            with publication._publication_lock():
                pass
        assert not lock.exists()


def test_lock_identity_retries_same_descriptor_and_retains_if_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = tmp_path / ".publication-lock"
    monkeypatch.setattr(publication, "PUBLICATION_LOCK", lock)
    real_fstat = publication.os.fstat
    calls = 0

    def fail_once(descriptor: int):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("injected one-shot fstat failure")
        return real_fstat(descriptor)

    monkeypatch.setattr(publication.os, "fstat", fail_once)
    with publication._publication_lock():
        assert lock.exists()
    assert calls == 2
    assert not lock.exists()

    def always_fail(_descriptor: int):
        raise OSError("injected persistent fstat failure")

    monkeypatch.setattr(publication.os, "fstat", always_fail)
    with pytest.raises(
        publication.CtrlSPublicationError,
        match="identity unavailable.*retained",
    ):
        with publication._publication_lock():
            pass
    assert lock.exists()
    assert lock.stat().st_size == 0
    lock.unlink()


def test_second_stage_creation_failure_cleans_first_owned_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, artifacts = _configure_private_publication(tmp_path, monkeypatch)
    real_mkdtemp = publication.tempfile.mkdtemp
    calls = 0

    def fail_second(*args: object, **kwargs: object) -> str:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected second-stage failure")
        return real_mkdtemp(*args, **kwargs)

    monkeypatch.setattr(publication.tempfile, "mkdtemp", fail_second)
    with pytest.raises(OSError, match="injected second-stage failure"):
        publication.preflight(recorded_at=_future(30))
    assert not list(sources.iterdir())
    assert not list(artifacts.iterdir())
    assert not publication.ARTIFACT.exists()


def test_initial_stage_identity_failure_never_adopts_substituted_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, artifacts = _configure_private_publication(tmp_path, monkeypatch)
    real_fstat = publication.os.fstat
    calls = 0
    foreign_stage: Path | None = None

    def substitute_then_fail(descriptor: int):
        nonlocal calls, foreign_stage
        calls += 1
        if calls in (2, 3):
            if calls == 2:
                stages = list(artifacts.glob(f".{publication.ARTIFACT_ID}.stage-*"))
                assert len(stages) == 1
                foreign_stage = stages[0]
                foreign_stage.rmdir()
                foreign_stage.mkdir()
                (foreign_stage / "foreign-sentinel").write_text(
                    "do not delete", encoding="utf-8"
                )
            raise OSError("injected artifact identity failure")
        return real_fstat(descriptor)

    monkeypatch.setattr(publication.os, "fstat", substitute_then_fail)
    with pytest.raises(
        publication.CtrlSPublicationError, match="identity unavailable.*retained"
    ):
        publication.preflight(recorded_at=_future(30))
    assert not list(sources.iterdir())
    assert foreign_stage is not None
    assert (foreign_stage / "foreign-sentinel").read_text(encoding="utf-8") == (
        "do not delete"
    )
    shutil.rmtree(foreign_stage)


def test_one_shot_stage_fstat_failure_retries_and_cleans_owned_stages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, artifacts = _configure_private_publication(tmp_path, monkeypatch)
    real_fstat = publication.os.fstat
    calls = 0

    def fail_once(descriptor: int):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("injected one-shot stage fstat failure")
        return real_fstat(descriptor)

    monkeypatch.setattr(publication.os, "fstat", fail_once)
    result = publication.preflight(recorded_at=_future(30))
    assert result["source_stage_discarded"] is True
    assert result["artifact_stage_discarded"] is True
    assert calls >= 2
    assert not list(sources.iterdir())
    assert not list(artifacts.iterdir())


def test_saved_descendant_identity_refuses_foreign_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_private_publication(tmp_path, monkeypatch)
    prepared = publication._prepare(_future(30))
    target = prepared.source_stage / publication.CHANDANVELLY_SOURCE_FILENAME
    target.unlink()
    target.write_text("foreign descendant", encoding="utf-8")
    try:
        with pytest.raises(
            publication.CtrlSPublicationError, match="tree identity changed"
        ):
            publication._discard_owned_tree(
                prepared.source_stage, prepared.source_identities
            )
        assert target.read_text(encoding="utf-8") == "foreign descendant"
        assert (prepared.source_stage / publication.PHARMACITY_SOURCE_FILENAME).exists()
    finally:
        if prepared.artifact_stage.exists():
            publication._discard_owned_tree(
                prepared.artifact_stage, prepared.artifact_identities
            )
        if prepared.source_stage.exists():
            shutil.rmtree(prepared.source_stage)


def test_existing_identical_rejects_rechecksummed_manifest_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_private_publication(tmp_path, monkeypatch)
    recorded_at = _future(2)
    publication.build(recorded_at=recorded_at, publication_authorized=True)
    manifest_path = publication.ARTIFACT / "manifest.json"
    sidecar_path = publication.ARTIFACT / "manifest.sha256"
    publication.ARTIFACT.chmod(0o755)
    manifest_path.chmod(0o644)
    sidecar_path.chmod(0o644)
    manifest = json.loads(manifest_path.read_bytes())
    manifest["accepted_source_records"] = 3
    manifest["source_rights"] = "mutated rights assertion"
    manifest_path.write_bytes(publication._canonical(manifest))
    sidecar_path.write_text(
        f"{publication._sha256(manifest_path)}  manifest.json\n",
        encoding="utf-8",
    )
    manifest_path.chmod(0o444)
    sidecar_path.chmod(0o444)
    publication.ARTIFACT.chmod(0o555)
    with pytest.raises(
        publication.CtrlSPublicationError, match="accepted manifest differs"
    ):
        publication.build(
            recorded_at=recorded_at,
            publication_authorized=True,
        )


def test_temporal_guard_and_preflight_preserve_reviewed_inodes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "payload").write_text("x", encoding="utf-8")
    with pytest.raises(
        publication.CtrlSPublicationError, match="post-dates recorded_at"
    ):
        publication._assert_stage_precedes(
            stage, datetime.now(UTC) - timedelta(seconds=10)
        )

    _configure_private_publication(tmp_path / "publication", monkeypatch)
    before = (
        publication._identity(publication.REVIEWED_SOURCE_STAGE, directory=True),
        publication._identity(publication.REVIEWED_ARTIFACT_STAGE, directory=True),
        publication._identity(publication._raw_capture(), directory=True),
    )
    publication.preflight(recorded_at=_future(60))
    after = (
        publication._identity(publication.REVIEWED_SOURCE_STAGE, directory=True),
        publication._identity(publication.REVIEWED_ARTIFACT_STAGE, directory=True),
        publication._identity(publication._raw_capture(), directory=True),
    )
    assert after == before
