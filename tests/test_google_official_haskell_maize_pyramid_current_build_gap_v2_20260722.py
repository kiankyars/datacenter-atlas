from __future__ import annotations

from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import socket
import stat
import tempfile

import pytest
from unittest.mock import patch

from datacenter_atlas.datacenter_atlas import (
    google_official_haskell_maize_pyramid_current_build_gap_v2_20260722 as core,
)


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_FILE_PINS = {
    "README.md": (
        2_313,
        "03f52419aa228b04758dd1f252f0dcb52dcdc2f4f74109757171cae18366f250",
    ),
    "candidate-assessment.json": (
        9_216,
        "734dc0010c35a3f4a7e2b53254f5597afa80dbebc31f02c8005c3c64bedcb40c",
    ),
    "manifest.json": (
        7_745,
        "75b0abee276eecb7bfa0d32caf5341db6769d34ea71d6497ffd45225d5740f47",
    ),
    "manifest.sha256": (
        80,
        "51affc739f25e23250498a7afddbe7a979a1b197a6e7bd4e9469b526894ca7e9",
    ),
    "retrieval-inventory.json": (
        20_603,
        "c869758d04c7167276cd4dcdb2a0fc4d09f98b42b4f1742da32cf686b87861a7",
    ),
    "rights-and-disposition.json": (
        4_108,
        "59862d649e17a5d0eff064fb9e942616293791897ca8ed1d54bf0d69f108d6f3",
    ),
    "source-snapshot.json": (
        8_980,
        "b548f14ab3c72e7aebeded5deb032fcc52b4f52faf0e2e3a1532e42c9ae7d72a",
    ),
}
EXPECTED_LOGICAL_TREE_SHA256 = (
    "79b9ce0ca96969a597eaf9507b11a20a8918e73eecf36f476cae1657bd07e690"
)
EXPECTED_PHYSICAL_TREE_SHA256 = (
    "59308cdc266dc6da1a0b6919b07c09e7568e0cb4b8a56210be4b24ec1ad1b885"
)


class StopBeforePublication(RuntimeError):
    pass


def checkpoint(path: Path) -> tuple[int, str]:
    raw = path.read_bytes()
    return len(raw), hashlib.sha256(raw).hexdigest()


def offline(stack: ExitStack) -> None:
    failure = AssertionError("Google v2 attempted network access")
    for name in (
        "socket",
        "create_connection",
        "getaddrinfo",
        "gethostbyname",
        "gethostbyname_ex",
    ):
        stack.enter_context(patch.object(socket, name, side_effect=failure))


def write_stage(root: Path) -> tuple[Path, core.ArtifactBundle]:
    root.mkdir(parents=True, exist_ok=True)
    stage = root / "artifact"
    stage.mkdir()
    bundle = core.build_bundle()
    core._write_stage(stage, bundle)
    return stage, bundle


def test_rejected_v1_incident_pins_all_seven_failed_member_ctimes() -> None:
    artifact = ROOT / core.REJECTED_V1_PATH
    before = {
        member.name: (
            *checkpoint(member),
            member.stat(follow_symlinks=False).st_ctime_ns,
        )
        for member in artifact.iterdir()
    }
    core._require_v1_incident()
    assert stat.S_IMODE(artifact.stat().st_mode) == 0o555
    assert artifact.stat().st_ctime_ns == core.REJECTED_V1_ROOT_CTIME_NS
    assert core.v1.tree_digest(artifact) == core.REJECTED_V1_PHYSICAL_TREE_SHA256
    target = core._instant(core.REJECTED_V1_RECORDED_AT).timestamp()
    assert set(before) == set(core.REJECTED_V1_MEMBER_PINS)
    assert all(
        artifact.joinpath(name).stat().st_ctime < target
        for name in core.REJECTED_V1_MEMBER_PINS
    )
    assert before == {
        name: (size, digest, ctime_ns)
        for name, (size, digest, ctime_ns) in core.REJECTED_V1_MEMBER_PINS.items()
    }
    assert core.INCIDENT_LINEAGE["accepted_as_base"] is False
    assert core.INCIDENT_LINEAGE["status"] == "rejected_publication_incident"
    assert "all seven" in core.INCIDENT_LINEAGE["reason"].casefold()


def test_exact_three_source_reuse_and_bounded_semantics() -> None:
    before = {
        name: (
            *checkpoint(core.SOURCES_ROOT / name),
            (core.SOURCES_ROOT / name).stat(follow_symlinks=False).st_ctime_ns,
        )
        for name in core.SOURCE_FILENAMES
    }
    documents = core._require_sources()
    assert len(documents) == 3
    assert before == {
        name: (*core.SOURCE_PINS[name], core.SOURCE_CTIME_NS[name])
        for name in core.SOURCE_FILENAMES
    }
    assert core._source_reuse()["new_source_files_created"] is False
    assert sum(len(document["evidence"]) for document in documents.values()) == 8
    assert sum(
        1 for document in documents.values() for _entity in ("campus", "project")
    ) == 6
    lifecycle = {
        (row["value"], row["as_of_date"])
        for document in documents.values()
        for row in document["lifecycle"]
    }
    assert lifecycle == {
        ("under_construction", "2025-11-30"),
        ("site_preparation", "2025-09-24"),
        ("under_construction", "2025-10-02"),
    }
    for document in documents.values():
        assert document["capacities"] == []
        assert document["workloads"] == []
        assert document["operating_models"] == []
        for entity in ("campus", "project"):
            assert document[entity]["coordinates"] is None
            assert document[entity]["geometry"] is None
    pyramid = documents[
        "curated-official-2026-07-22-google-west-memphis-project-pyramid-current-build.json"
    ]
    serialized = json.dumps(pyramid, sort_keys=True).casefold()
    for token in ("500/230", "voltage_kv", '"latitude"', '"longitude"'):
        assert token not in serialized
    assessment = json.loads(core.build_bundle().files["candidate-assessment.json"])
    assert [row["candidate_id"] for row in assessment["candidates"][3:]] == [
        "google-new-florence-project-spade",
        "google-pine-island-project-skyway",
        "google-hermantown-potential-campus",
    ]
    assert before == {
        name: (
            *checkpoint(core.SOURCES_ROOT / name),
            (core.SOURCES_ROOT / name).stat(follow_symlinks=False).st_ctime_ns,
        )
        for name in core.SOURCE_FILENAMES
    }


def test_deterministic_double_build_offline_validation_and_trees() -> None:
    with ExitStack() as stack:
        offline(stack)
        first = core.build_bundle()
        second = core.build_bundle()
    assert first == second
    assert set(first.files) == core.CLOSED_FILES
    assert first.manifest["source_reuse"]["exact_reused_source_count"] == 3
    assert first.manifest["release_integration"] == "none"
    assert first.manifest["open_seed_successor_created"] is False
    assert first.manifest["incident_lineage"] == core.INCIDENT_LINEAGE
    with tempfile.TemporaryDirectory(prefix="google-v2-replay-", dir="/private/tmp") as tmp:
        root = Path(tmp)
        first_stage, _ = write_stage(root / "one")
        second_stage, _ = write_stage(root / "two")
        with ExitStack() as stack:
            offline(stack)
            manifest = core.validate_artifact(
                first_stage,
                require_live=False,
                wall_clock=core._instant(core.RECORDED_AT),
            )
        assert manifest == first.manifest
        assert core.v1.tree_digest(first_stage) == core.v1.tree_digest(second_stage)
        assert manifest["tree_sha256"] == core.v1._file_tree(manifest["files"])


def test_ctime_refresh_covers_all_seven_children_and_root() -> None:
    with tempfile.TemporaryDirectory(prefix="google-v2-ctime-", dir="/private/tmp") as tmp:
        root = Path(tmp)
        stage, _ = write_stage(root)
        target = datetime.now(UTC)
        core._refresh_stage_ctimes(stage, target)
        paths = core._artifact_paths(stage)
        assert len(paths) == 8
        core._assert_chronology(paths, target, require_final_ctime=True)
        for path in paths:
            metadata = path.stat(follow_symlinks=False)
            assert metadata.st_birthtime <= target.timestamp()
            assert metadata.st_mtime <= target.timestamp()
            assert metadata.st_ctime >= target.timestamp()
            assert stat.S_IMODE(metadata.st_mode) == (
                0o555 if path == stage else 0o444
            )


def test_collision_hidden_barrier_and_final_validation_rollback(tmp_path: Path) -> None:
    target = core._instant(core.RECORDED_AT)
    fake_now = target - timedelta(seconds=90)
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    final = artifact_root / core.ARTIFACT_ID
    lock = tmp_path / ".lock"
    final.mkdir()
    with ExitStack() as stack:
        offline(stack)
        stack.enter_context(patch.object(core, "ARTIFACT_ROOT", artifact_root))
        stack.enter_context(patch.object(core, "ARTIFACT", final))
        stack.enter_context(patch.object(core, "PUBLICATION_LOCK", lock))
        stack.enter_context(patch.object(core, "_now", return_value=fake_now))
        with pytest.raises(
            core.GoogleCurrentBuildGapV2Error, match="refusing replacement"
        ):
            core.publish_artifact()

    final.rmdir()

    def stop_at_barrier(actual: datetime) -> None:
        assert actual == target
        assert not final.exists() and not final.is_symlink()
        raise StopBeforePublication("v2 final remained hidden")

    with ExitStack() as stack:
        offline(stack)
        stack.enter_context(patch.object(core, "ARTIFACT_ROOT", artifact_root))
        stack.enter_context(patch.object(core, "ARTIFACT", final))
        stack.enter_context(patch.object(core, "PUBLICATION_LOCK", lock))
        stack.enter_context(patch.object(core, "_now", return_value=fake_now))
        stack.enter_context(patch.object(core, "_assert_chronology", return_value=None))
        stack.enter_context(patch.object(core, "_wait_until", side_effect=stop_at_barrier))
        with pytest.raises(StopBeforePublication, match="v2 final remained hidden"):
            core.publish_artifact()
    assert not final.exists() and not final.is_symlink()
    assert not lock.exists() and not lock.is_symlink()

    real_validate = core.validate_artifact

    def fail_final(path: Path | None = None, **kwargs: object) -> dict[str, object]:
        if path is None:
            raise RuntimeError("simulated v2 final validation failure")
        return real_validate(path, **kwargs)

    with ExitStack() as stack:
        offline(stack)
        stack.enter_context(patch.object(core, "ARTIFACT_ROOT", artifact_root))
        stack.enter_context(patch.object(core, "ARTIFACT", final))
        stack.enter_context(patch.object(core, "PUBLICATION_LOCK", lock))
        stack.enter_context(patch.object(core, "_now", return_value=fake_now))
        stack.enter_context(patch.object(core, "_assert_chronology", return_value=None))
        stack.enter_context(patch.object(core, "_wait_until", return_value=None))
        stack.enter_context(patch.object(core, "_refresh_stage_ctimes", return_value=None))
        stack.enter_context(patch.object(core, "validate_artifact", side_effect=fail_final))
        with pytest.raises(RuntimeError, match="simulated v2 final validation failure"):
            core.publish_artifact()
    assert not final.exists() and not final.is_symlink()
    assert not lock.exists() and not lock.is_symlink()
    assert not list(artifact_root.glob(f".{core.ARTIFACT_ID}.stage-*"))


def test_published_v2_when_present() -> None:
    if not core.ARTIFACT.exists():
        return
    with ExitStack() as stack:
        offline(stack)
        first = core.validate_artifact()
        second = core.validate_artifact()
    assert first == second
    assert first["artifact_id"] == core.ARTIFACT_ID
    assert first["recorded_at"] == core.RECORDED_AT
    assert first["incident_lineage"] == core.INCIDENT_LINEAGE
    assert {
        member.name: checkpoint(member) for member in core.ARTIFACT.iterdir()
    } == EXPECTED_FILE_PINS
    assert first["tree_sha256"] == EXPECTED_LOGICAL_TREE_SHA256
    assert core.v1.tree_digest(core.ARTIFACT) == EXPECTED_PHYSICAL_TREE_SHA256
    paths = core._artifact_paths(core.ARTIFACT)
    target = core._instant(core.RECORDED_AT)
    core._assert_chronology(paths, target, require_final_ctime=True)
    assert len(paths) == 8
    for path in paths:
        metadata = path.stat(follow_symlinks=False)
        assert metadata.st_birthtime <= target.timestamp()
        assert metadata.st_mtime <= target.timestamp()
        assert metadata.st_ctime >= target.timestamp()
        assert stat.S_IMODE(metadata.st_mode) == (
            0o555 if path == core.ARTIFACT else 0o444
        )
