from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from datacenter_atlas.datacenter_atlas import construction_timeline_v11 as timeline
from datacenter_atlas.open_seed_v56 import tree_digest

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
V10_BUNDLE = ROOT / "construction_timelines/2026-07-21-public-open-v10"


def _future(minutes: int = 10) -> str:
    target = datetime.now(UTC).replace(microsecond=0) + timedelta(
        minutes=minutes
    )
    return target.isoformat(timespec="seconds").replace("+00:00", "Z")


def _offline_stack() -> tuple[patch, ...]:
    failure = AssertionError("construction timeline v11 attempted network access")
    return tuple(
        patch.object(socket, name, side_effect=failure)
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        )
    )


def _set_output_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, Path]:
    sources = tmp_path / "sources"
    bundles = tmp_path / "construction_timelines"
    sources.mkdir()
    bundles.mkdir()
    definition = sources / timeline.DEFINITION.name
    bundle = bundles / timeline.BUNDLE.name
    lock = tmp_path / timeline.PUBLICATION_LOCK.name
    monkeypatch.setattr(timeline, "DEFINITION", definition)
    monkeypatch.setattr(timeline, "BUNDLE", bundle)
    monkeypatch.setattr(timeline, "PUBLICATION_LOCK", lock)
    return definition, bundle, lock


def _frozen_roundtrip_stages(
    definition: Path, bundle: Path
) -> tuple[tuple[int, int], dict[str, tuple[str, int, int]]]:
    definition.write_bytes(b"definition\n")
    bundle.mkdir()
    (bundle / "payload").write_bytes(b"payload\n")
    identities = timeline._tree_identities(bundle)
    timeline._freeze(definition, bundle)
    return timeline._identity(definition, directory=False), identities


def _install_fast_publisher_gates(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    payloads = {
        name: f"private test payload: {name}\n".encode()
        for name in timeline.BUNDLE_FILES
    }
    manifest: dict[str, object] = {"counts": dict(timeline.EXPECTED_COUNTS)}
    guard = {"accepted-inputs": "unchanged"}
    monkeypatch.setattr(
        timeline, "_prepare_payloads", lambda _definition: (payloads, manifest)
    )
    monkeypatch.setattr(
        timeline,
        "validate_construction_timeline_bundle",
        lambda *_args, **_kwargs: manifest,
    )
    monkeypatch.setattr(
        timeline, "_validate_two_replays", lambda *_args, **_kwargs: "a" * 64
    )
    monkeypatch.setattr(
        timeline, "_validate_publication_times", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(timeline, "_wait_until", lambda _target: None)
    monkeypatch.setattr(timeline, "_input_guard_state", lambda: guard)
    monkeypatch.setattr(timeline, "_reviewed_input_guard", lambda: guard)
    return guard


@pytest.fixture(scope="module")
def reconstructed() -> tuple[list[dict], list[dict], dict, list[dict]]:
    observations, additions, provenance = timeline._reconstruct_observations()
    timelines = timeline._timeline_rows(observations, additions)
    return observations, additions, provenance, timelines


def test_all_inputs_and_full_manifests_are_hash_pinned_and_canonical() -> None:
    timeline._validate_input_pins()
    assert tree_digest(V10_BUNDLE) == timeline.PREDECESSOR_TREE_SHA256
    for spec in timeline.RELEASE_SPECS:
        assert tree_digest(spec.release) == spec.tree_sha256
        assert timeline._file_pin(spec.definition) == spec.definition_pin
        assert timeline._file_pin(spec.release / "manifest.json") == spec.manifest_pin
        raw = (spec.release / "manifest.json").read_bytes()
        document = json.loads(raw)
        assert raw == timeline.CODEC._canonical_json(document)
        assert document["recorded_at"] == spec.recorded_at


def test_every_v10_observation_is_byte_exact_and_delta_is_exact(
    reconstructed: tuple[list[dict], list[dict], dict, list[dict]],
) -> None:
    observations, additions, provenance, _timelines = reconstructed
    predecessor = timeline.CODEC._parse_csv(V10_BUNDLE / timeline.OBSERVATIONS_FILENAME)
    by_id = {row["observation_id"]: row for row in observations}
    assert (len(predecessor), len(observations), len(additions)) == (571, 607, 36)
    for row in predecessor:
        inherited = by_id[row["observation_id"]]
        assert inherited == row
        assert timeline.CODEC._csv_bytes([inherited]) == timeline.CODEC._csv_bytes(
            [row]
        )
    assert len({row["entity_stable_key"] for row in additions}) == 34
    assert (
        len(
            {row["entity_stable_key"] for row in additions}
            - {row["entity_stable_key"] for row in predecessor}
        )
        == 33
    )
    assert (
        timeline._event_contract_sha256(timeline._event_contract(additions, provenance))
        == timeline.ADDITION_EVENT_CONTRACT_SHA256
    )


def test_only_fin04_grouped_row_is_replaced_and_topology_is_exact(
    reconstructed: tuple[list[dict], list[dict], dict, list[dict]],
) -> None:
    _observations, _additions, _provenance, timelines = reconstructed
    predecessor = timeline.CODEC._parse_jsonl(V10_BUNDLE / timeline.TIMELINES_FILENAME)
    current = {row["entity_stable_key"]: row for row in timelines}
    assert (len(predecessor), len(timelines)) == (550, 583)
    for row in predecessor:
        key = row["entity_stable_key"]
        if key == timeline.FIN04_KEY:
            continue
        assert current[key] == row
        assert timeline.CODEC._canonical_json_line(
            current[key]
        ) == timeline.CODEC._canonical_json_line(row)

    fin04 = current[timeline.FIN04_KEY]
    assert [(row["observed_date"], row["status"]) for row in fin04["observations"]] == [
        ("2026-07-20", "under_construction"),
        ("2026-07-21", "under_construction"),
    ]
    assert fin04["has_multiple_observations"] is True
    assert fin04["has_status_change"] is False
    assert [
        row["status"] for row in current[timeline.WOOD_DALE_KEY]["observations"]
    ] == ["shell", "under_construction"]
    assert [
        row["status"] for row in current[timeline.BEALE_TULSA_KEY]["observations"]
    ] == ["under_construction", "under_construction"]

    multi = [row for row in timelines if row["has_multiple_observations"]]
    changing = [row for row in multi if row["has_status_change"]]
    repeated = [row for row in multi if not row["has_status_change"]]
    single_old = [
        row
        for row in timelines
        if not row["has_multiple_observations"]
        and row["single_old_observation_current_unknown"]
    ]
    assert (len(multi), len(repeated), len(changing), len(single_old)) == (
        24,
        9,
        15,
        38,
    )
    assert all(row["current_status_classification"] == "unknown" for row in timelines)
    assert all(row["current_construction_claim"] is False for row in timelines)
    for key in timeline.STALE_CURRENT_UNKNOWN_KEYS:
        assert current[key]["current_status_classification"] == "unknown"
        assert current[key]["latest_observation_persistence_assumed"] is False


def test_coverage_and_manifest_have_exact_governed_counts(
    reconstructed: tuple[list[dict], list[dict], dict, list[dict]],
) -> None:
    observations, additions, provenance, timelines = reconstructed
    generated_at = _future()
    raw = timeline.CODEC._canonical_json(timeline._definition_document(generated_at))
    definition = timeline._Definition(
        path=timeline.DEFINITION,
        raw=raw,
        timeline_id=timeline.TIMELINE_ID,
        as_of=timeline.AS_OF,
        generated_at=generated_at,
        expected=timeline.EXPECTED_COUNTS,
    )
    coverage = timeline._coverage(
        observations, additions, provenance, timelines, definition
    )
    assert coverage["counts"] == timeline.EXPECTED_COUNTS
    assert coverage["open_seed_release_event_counts"] == {
        "2026-07-21-open-seed-v93": 3,
        "2026-07-21-open-seed-v94": 11,
        "2026-07-22-open-seed-v95": 9,
        "2026-07-22-open-seed-v96": 10,
        "2026-07-22-open-seed-v97": 3,
    }
    assert coverage["lineage_aware_source_family_count"] == 297
    assert coverage["v11_delta_inference_guardrails"] == timeline.INFERENCE_GUARDRAILS
    assert coverage["v11_delta_operational_lifecycle_closures"] == []
    assert coverage["stale_current_unknown_project_keys"] == sorted(
        timeline.STALE_CURRENT_UNKNOWN_KEYS
    )


def test_real_prepublication_is_two_replay_and_leaves_no_final_or_stage() -> None:
    contexts = _offline_stack()
    with contexts[0], contexts[1], contexts[2], contexts[3], contexts[4]:
        result = timeline.prepare_construction_timeline_v11(_future())
    assert result["status"] == "prepublication-validated"
    assert result["publication_authorized"] is False
    assert result["counts"] == timeline.EXPECTED_COUNTS
    assert result["addition_event_contract_sha256"] == (
        timeline.ADDITION_EVENT_CONTRACT_SHA256
    )
    assert (
        result["bundle_files"][timeline.MANIFEST_FILENAME]["sha256"]
        == result["two_replay_manifest_sha256"]
    )
    assert result["private_no_replace_roundtrip_validated"] is True
    assert result["final_definition_absent"] is True
    assert result["final_bundle_absent"] is True
    assert result["publication_lock_absent"] is True
    assert not timeline.DEFINITION.exists()
    assert not timeline.BUNDLE.exists()
    assert not timeline.PUBLICATION_LOCK.exists()
    assert timeline._stage_paths() == []


def test_authorization_replay_count_collision_and_runner_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(
        timeline.ConstructionTimelineV11Error, match="explicit authorization"
    ):
        timeline.publish_construction_timeline_v11()
    with pytest.raises(timeline.ConstructionTimelineV11Error, match="exactly two"):
        timeline.prepare_construction_timeline_v11(_future(), replay_count=1)

    sources = tmp_path / "sources"
    bundles = tmp_path / "construction_timelines"
    sources.mkdir()
    bundles.mkdir()
    definition = sources / timeline.DEFINITION.name
    bundle = bundles / timeline.BUNDLE.name
    lock = tmp_path / timeline.PUBLICATION_LOCK.name
    monkeypatch.setattr(timeline, "DEFINITION", definition)
    monkeypatch.setattr(timeline, "BUNDLE", bundle)
    monkeypatch.setattr(timeline, "PUBLICATION_LOCK", lock)
    definition.write_text("collision")
    with pytest.raises(timeline.ConstructionTimelineV11Error, match="partial"):
        timeline.publish_construction_timeline_v11(
            _future(), publication_authorized=True
        )
    assert definition.read_text() == "collision"
    assert not bundle.exists()
    assert not lock.exists()

    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/build_construction_timeline_v11.py"),
            "--help",
        ],
        cwd=WORKSPACE,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "--publish-authorized" in completed.stdout

    prepared = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/prepare_construction_timeline_v11.py"),
            "--help",
        ],
        cwd=WORKSPACE,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert prepared.returncode == 0, prepared.stderr
    assert "--publish-authorized" not in prepared.stdout
    rejected = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/prepare_construction_timeline_v11.py"),
            "--publish-authorized",
        ],
        cwd=WORKSPACE,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert rejected.returncode == 2
    assert "unrecognized arguments: --publish-authorized" in rejected.stderr


def test_active_lock_wins_even_when_both_final_paths_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    definition, bundle, lock = _set_output_paths(tmp_path, monkeypatch)
    definition.write_bytes(b"existing definition")
    bundle.mkdir()
    lock.write_text("pid=foreign\n")

    with pytest.raises(timeline.ConstructionTimelineV11Error, match="active.*lock"):
        timeline.publish_construction_timeline_v11(
            _future(), publication_authorized=True
        )

    assert definition.read_bytes() == b"existing definition"
    assert bundle.is_dir()
    assert lock.read_text() == "pid=foreign\n"


def test_fstat_retry_and_unknown_lock_are_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _definition, _bundle, lock = _set_output_paths(tmp_path, monkeypatch)
    descriptor = os.open(tmp_path, os.O_RDONLY)
    real_fstat = os.fstat
    calls: list[int] = []

    def flaky_fstat(value: int) -> os.stat_result:
        calls.append(value)
        if len(calls) == 1:
            raise OSError("injected one-shot fstat failure")
        return real_fstat(value)

    monkeypatch.setattr(timeline.os, "fstat", flaky_fstat)
    try:
        identity = timeline._fstat_identity_with_retry(
            descriptor,
            expected_kind="directory",
            label="retry proof",
        )
    finally:
        os.close(descriptor)
    assert calls == [descriptor, descriptor]
    assert identity[:2] == (
        tmp_path.stat(follow_symlinks=False).st_dev,
        tmp_path.stat(follow_symlinks=False).st_ino,
    )

    monkeypatch.setattr(timeline.os, "fstat", real_fstat)
    real_retry = timeline._fstat_identity_with_retry

    def reject_lock(
        value: int,
        *,
        expected_kind: str,
        label: str,
        expected_mode: int | None = None,
        attempts: int = 2,
    ) -> tuple[int, int, str]:
        if label == "timeline v11 publication lock":
            raise timeline.ConstructionTimelineV11Error(
                "injected persistent lock identity failure"
            )
        return real_retry(
            value,
            expected_kind=expected_kind,
            label=label,
            expected_mode=expected_mode,
            attempts=attempts,
        )

    monkeypatch.setattr(timeline, "_fstat_identity_with_retry", reject_lock)
    with (
        timeline._bound_output_parents() as bindings,
        pytest.raises(
            timeline.ConstructionTimelineV11Error,
            match="persistent lock identity failure",
        ),
        timeline._publication_lock(bindings),
    ):
        pytest.fail("unknown lock was adopted")
    assert lock.is_file()
    assert stat_mode(lock) == 0o600


def stat_mode(path: Path) -> int:
    return path.stat(follow_symlinks=False).st_mode & 0o777


def test_definition_stage_creation_is_bound_during_parent_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    definition, _bundle, _lock = _set_output_paths(tmp_path, monkeypatch)
    bound_parent = definition.parent
    displaced_parent = tmp_path / "sources.bound-displaced"
    replacement_parent = tmp_path / "sources.replacement"
    replacement_parent.mkdir()
    real_open = timeline.os.open
    stage_name: str | None = None

    def swap_on_definition_create(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal stage_name
        candidate = os.fsdecode(path)
        if (
            stage_name is None
            and dir_fd is not None
            and flags & os.O_CREAT
            and candidate.startswith(f".{definition.name}.private-stage-")
        ):
            stage_name = candidate
            bound_parent.rename(displaced_parent)
            replacement_parent.rename(bound_parent)
            (bound_parent / candidate).write_bytes(b"foreign definition stage")
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(timeline.os, "open", swap_on_definition_create)
    try:
        with (
            timeline._bound_output_parents() as bindings,
            pytest.raises(
                timeline.ConstructionTimelineV11Error,
                match="parent identity changed",
            ),
        ):
            timeline._write_definition_stage(b"owned", parent_bindings=bindings)
        assert stage_name is not None
        assert not (displaced_parent / stage_name).exists()
        assert (bound_parent / stage_name).read_bytes() == b"foreign definition stage"
        assert not definition.exists()
    finally:
        if stage_name is not None:
            bound_parent.rename(replacement_parent)
            displaced_parent.rename(bound_parent)


def test_bundle_root_creation_is_bound_during_parent_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _definition, bundle, _lock = _set_output_paths(tmp_path, monkeypatch)
    bound_parent = bundle.parent
    displaced_parent = tmp_path / "bundles.bound-displaced"
    replacement_parent = tmp_path / "bundles.replacement"
    replacement_parent.mkdir()
    real_mkdir = timeline.os.mkdir
    stage_name: str | None = None

    def swap_on_bundle_root_create(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> None:
        nonlocal stage_name
        candidate = os.fsdecode(path)
        if (
            stage_name is None
            and dir_fd is not None
            and candidate.startswith(f".{bundle.name}.private-stage-")
        ):
            stage_name = candidate
            bound_parent.rename(displaced_parent)
            replacement_parent.rename(bound_parent)
            foreign = bound_parent / candidate
            foreign.mkdir()
            (foreign / "foreign-sentinel").write_bytes(b"preserve root")
        real_mkdir(path, mode, dir_fd=dir_fd)

    monkeypatch.setattr(timeline.os, "mkdir", swap_on_bundle_root_create)
    try:
        with (
            timeline._bound_output_parents() as bindings,
            pytest.raises(
                timeline.ConstructionTimelineV11Error,
                match="parent identity changed",
            ),
        ):
            timeline._write_bundle_stage(
                {"payload": b"owned"},
                parent_bindings=bindings,
            )
        assert stage_name is not None
        assert not (displaced_parent / stage_name).exists()
        assert (
            bound_parent / stage_name / "foreign-sentinel"
        ).read_bytes() == b"preserve root"
        assert not bundle.exists()
    finally:
        if stage_name is not None:
            bound_parent.rename(replacement_parent)
            displaced_parent.rename(bound_parent)


def test_bundle_member_creation_is_root_dirfd_bound_during_parent_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _definition, bundle, _lock = _set_output_paths(tmp_path, monkeypatch)
    bound_parent = bundle.parent
    displaced_parent = tmp_path / "bundles.bound-displaced"
    replacement_parent = tmp_path / "bundles.replacement"
    replacement_parent.mkdir()
    real_open = timeline.os.open
    stage_name: str | None = None

    def swap_on_bundle_member_create(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal stage_name
        candidate = os.fsdecode(path)
        if (
            stage_name is None
            and candidate == "payload"
            and dir_fd is not None
            and flags & os.O_CREAT
        ):
            owned_root = next(bound_parent.glob(f".{bundle.name}.private-stage-*"))
            stage_name = owned_root.name
            bound_parent.rename(displaced_parent)
            replacement_parent.rename(bound_parent)
            foreign = bound_parent / stage_name
            foreign.mkdir()
            (foreign / "foreign-sentinel").write_bytes(b"preserve member root")
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(timeline.os, "open", swap_on_bundle_member_create)
    try:
        with (
            timeline._bound_output_parents() as bindings,
            pytest.raises(
                timeline.ConstructionTimelineV11Error,
                match="parent identity changed",
            ),
        ):
            timeline._write_bundle_stage(
                {"payload": b"owned"},
                parent_bindings=bindings,
            )
        assert stage_name is not None
        assert not (displaced_parent / stage_name).exists()
        assert (
            bound_parent / stage_name / "foreign-sentinel"
        ).read_bytes() == b"preserve member root"
        assert not bundle.exists()
    finally:
        if stage_name is not None:
            bound_parent.rename(replacement_parent)
            displaced_parent.rename(bound_parent)


def test_bound_bundle_root_and_member_fstat_substitution_is_retained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _definition, bundle, _lock = _set_output_paths(tmp_path, monkeypatch)
    real_retry = timeline._fstat_identity_with_retry
    state: dict[str, Path | bool] = {"root_swapped": False}
    monkeypatch.setattr(timeline.secrets, "token_hex", lambda _length: "rootproof")

    def substitute_root(
        descriptor: int,
        *,
        expected_kind: str,
        label: str,
        expected_mode: int | None = None,
        attempts: int = 2,
    ) -> tuple[int, int, str]:
        details = real_retry(
            descriptor,
            expected_kind=expected_kind,
            label=label,
            expected_mode=expected_mode,
            attempts=attempts,
        )
        if label == "timeline v11 bundle stage root" and not state["root_swapped"]:
            stage = bundle.parent / f".{bundle.name}.private-stage-rootproof"
            orphan = stage.with_name(f"{stage.name}.owned-orphan")
            stage.rename(orphan)
            stage.mkdir()
            state.update(root_swapped=True, stage=stage, orphan=orphan)
        return details

    monkeypatch.setattr(timeline, "_fstat_identity_with_retry", substitute_root)
    with (
        timeline._bound_output_parents() as bindings,
        pytest.raises(
            timeline.ConstructionTimelineV11Error,
            match="differs from its descriptor",
        ) as raised,
    ):
        timeline._write_bundle_stage(
            {"payload": b"owned"},
            parent_bindings=bindings,
        )
    stage = state["stage"]
    orphan = state["orphan"]
    assert isinstance(stage, Path) and stage.is_dir()
    assert isinstance(orphan, Path) and orphan.is_dir()
    assert any("retained fail-closed" in note for note in raised.value.__notes__)

    state = {"member_swapped": False}
    monkeypatch.setattr(timeline.secrets, "token_hex", lambda _length: "memberproof")
    monkeypatch.setattr(timeline, "_fstat_identity_with_retry", real_retry)

    def substitute_member(
        descriptor: int,
        *,
        expected_kind: str,
        label: str,
        expected_mode: int | None = None,
        attempts: int = 2,
    ) -> tuple[int, int, str]:
        details = real_retry(
            descriptor,
            expected_kind=expected_kind,
            label=label,
            expected_mode=expected_mode,
            attempts=attempts,
        )
        if label.endswith("bundle member payload") and not state["member_swapped"]:
            root = bundle.parent / f".{bundle.name}.private-stage-memberproof"
            member = root / "payload"
            orphan_member = root / "payload.owned-orphan"
            member.rename(orphan_member)
            member.write_bytes(b"foreign replacement")
            state.update(
                member_swapped=True,
                root=root,
                orphan_member=orphan_member,
            )
        return details

    monkeypatch.setattr(timeline, "_fstat_identity_with_retry", substitute_member)
    with (
        timeline._bound_output_parents() as bindings,
        pytest.raises(
            timeline.ConstructionTimelineV11Error,
            match="was substituted",
        ) as member_raised,
    ):
        timeline._write_bundle_stage(
            {"payload": b"owned"},
            parent_bindings=bindings,
        )
    member_root = state["root"]
    assert isinstance(member_root, Path)
    assert (member_root / "payload").read_bytes() == b"foreign replacement"
    assert (member_root / "payload.owned-orphan").is_file()
    assert any("retained fail-closed" in note for note in member_raised.value.__notes__)


@pytest.mark.parametrize("raise_after", ["bundle", "definition"])
def test_private_roundtrip_recovers_when_helper_raises_after_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raise_after: str
) -> None:
    definition_final, bundle_final, _lock = _set_output_paths(tmp_path, monkeypatch)
    definition_stage = definition_final.parent / ".definition.private-stage-test.json"
    bundle_stage = bundle_final.parent / ".bundle.private-stage-test"
    definition_identity, bundle_identities = _frozen_roundtrip_stages(
        definition_stage, bundle_stage
    )
    real_rename = timeline._rename_noreplace_at
    injected = False

    def success_then_raise(
        parent_descriptor: int, source_name: str, destination_name: str
    ) -> None:
        nonlocal injected
        real_rename(parent_descriptor, source_name, destination_name)
        is_bundle = destination_name.startswith(f".{bundle_final.name}.roundtrip-")
        is_definition = destination_name.startswith(
            f".{definition_final.name}.roundtrip-"
        )
        if not injected and (
            (raise_after == "bundle" and is_bundle)
            or (raise_after == "definition" and is_definition)
        ):
            injected = True
            raise timeline.ConstructionTimelineV11Error(
                "injected helper failure after successful promotion"
            )

    monkeypatch.setattr(timeline, "_rename_noreplace_at", success_then_raise)
    with timeline._bound_output_parents() as bindings:
        with pytest.raises(
            timeline.ConstructionTimelineV11Error,
            match="after successful promotion",
        ):
            timeline._private_promotion_roundtrip(
                definition_stage,
                bundle_stage,
                definition_identity=definition_identity,
                bundle_identities=bundle_identities,
                parent_bindings=bindings,
            )
        assert timeline._bound_identity(
            bindings, definition_stage, definition_identity, directory=False
        )
        timeline._assert_bound_tree_identities(
            bindings, bundle_stage, bundle_identities
        )
        assert not any(
            path.name.startswith(f".{definition_final.name}.roundtrip-")
            or path.name.startswith(f".{bundle_final.name}.roundtrip-")
            for parent in (definition_final.parent, bundle_final.parent)
            for path in parent.iterdir()
        )


def test_parent_swap_inside_promotion_cannot_redirect_owned_inode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    definition, _bundle, _lock = _set_output_paths(tmp_path, monkeypatch)
    stage = definition.parent / ".definition.private-stage-test.json"
    stage.write_bytes(b"owned inode")
    stage.chmod(0o444)
    identity = timeline._identity(stage, directory=False)
    bound_parent = definition.parent
    displaced_parent = tmp_path / "sources.bound-displaced"
    replacement_parent = tmp_path / "sources.replacement"
    replacement_parent.mkdir()
    real_rename = timeline._rename_noreplace_at

    def swap_rehome_then_call(
        parent_descriptor: int, source_name: str, destination_name: str
    ) -> None:
        bound_parent.rename(displaced_parent)
        replacement_parent.rename(bound_parent)
        (displaced_parent / source_name).rename(bound_parent / source_name)
        real_rename(parent_descriptor, source_name, destination_name)

    monkeypatch.setattr(timeline, "_rename_noreplace_at", swap_rehome_then_call)
    with timeline._bound_output_parents() as bindings:
        with pytest.raises(timeline.ConstructionTimelineV11Error):
            timeline._promote_noreplace_checked(
                stage,
                definition,
                directory=False,
                parent_bindings=bindings,
            )

        assert not definition.exists()
        assert not (displaced_parent / definition.name).exists()
        assert timeline._has_identity(
            bound_parent / stage.name, identity, directory=False
        )

        # Restore the lexical parent while the descriptor binding remains live.
        (bound_parent / stage.name).rename(displaced_parent / stage.name)
        bound_parent.rename(replacement_parent)
        displaced_parent.rename(bound_parent)
        assert timeline._has_identity(stage, identity, directory=False)


def test_successful_bound_move_rolls_back_after_parent_path_is_swapped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    definition, _bundle, _lock = _set_output_paths(tmp_path, monkeypatch)
    stage = definition.parent / ".definition.private-stage-test.json"
    stage.write_bytes(b"owned inode")
    stage.chmod(0o444)
    identity = timeline._identity(stage, directory=False)
    bound_parent = definition.parent
    displaced_parent = tmp_path / "sources.bound-displaced"
    replacement_parent = tmp_path / "sources.replacement"
    replacement_parent.mkdir()
    real_rename = timeline._rename_noreplace_at
    injected = False

    def swap_then_move_in_bound_parent(
        parent_descriptor: int, source_name: str, destination_name: str
    ) -> None:
        nonlocal injected
        if not injected:
            bound_parent.rename(displaced_parent)
            replacement_parent.rename(bound_parent)
            injected = True
        real_rename(parent_descriptor, source_name, destination_name)

    monkeypatch.setattr(
        timeline, "_rename_noreplace_at", swap_then_move_in_bound_parent
    )
    with timeline._bound_output_parents() as bindings:
        with pytest.raises(
            timeline.ConstructionTimelineV11Error, match="parent identity changed"
        ):
            timeline._promote_noreplace_checked(
                stage,
                definition,
                directory=False,
                parent_bindings=bindings,
            )

        assert not definition.exists()
        assert timeline._has_identity(
            displaced_parent / definition.name, identity, directory=False
        )
        timeline._rollback_noreplace(
            definition,
            stage,
            identity,
            directory=False,
            parent_bindings=bindings,
        )
        assert not (displaced_parent / definition.name).exists()
        assert timeline._has_identity(
            displaced_parent / stage.name, identity, directory=False
        )

        bound_parent.rename(replacement_parent)
        displaced_parent.rename(bound_parent)
        assert timeline._has_identity(stage, identity, directory=False)


def test_publisher_dirfd_cleanup_removes_displaced_owned_stage_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    definition, bundle, lock = _set_output_paths(tmp_path, monkeypatch)
    _install_fast_publisher_gates(monkeypatch)
    bound_parent = bundle.parent
    displaced_parent = tmp_path / "bundles.bound-displaced"
    replacement_parent = tmp_path / "bundles.replacement"
    replacement_parent.mkdir()
    real_rename = timeline._rename_noreplace_at
    injected = False
    owned_stage_name: str | None = None

    def swap_parent_then_move_in_bound_parent(
        parent_descriptor: int, source_name: str, destination_name: str
    ) -> None:
        nonlocal injected, owned_stage_name
        if not injected and destination_name == bundle.name:
            owned_stage_name = source_name
            foreign_stage = replacement_parent / source_name
            foreign_stage.mkdir()
            (foreign_stage / "foreign-sentinel").write_bytes(b"preserve me")
            bound_parent.rename(displaced_parent)
            replacement_parent.rename(bound_parent)
            injected = True
        real_rename(parent_descriptor, source_name, destination_name)

    monkeypatch.setattr(
        timeline, "_rename_noreplace_at", swap_parent_then_move_in_bound_parent
    )
    try:
        with pytest.raises(
            timeline.ConstructionTimelineV11Error, match="parent identity changed"
        ):
            timeline.publish_construction_timeline_v11(
                _future(), publication_authorized=True
            )

        assert injected is True
        assert owned_stage_name is not None
        assert not bundle.exists()
        assert not (displaced_parent / bundle.name).exists()
        assert not (displaced_parent / owned_stage_name).exists()
        assert (
            bound_parent / owned_stage_name / "foreign-sentinel"
        ).read_bytes() == b"preserve me"
        assert not definition.exists()
        assert not any(definition.parent.glob(f".{definition.name}.private-stage-*"))
        assert not lock.exists()
    finally:
        if injected:
            bound_parent.rename(replacement_parent)
            displaced_parent.rename(bound_parent)


def test_bound_cleanup_is_recursive_and_preserves_replacement_parent_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    definition, bundle, _lock = _set_output_paths(tmp_path, monkeypatch)
    definition_stage = definition.parent / ".definition.private-stage-test.json"
    bundle_stage = bundle.parent / ".bundle.private-stage-test"
    definition_stage.write_bytes(b"owned definition")
    bundle_stage.mkdir()
    nested = bundle_stage / "nested"
    nested.mkdir()
    (nested / "payload").write_bytes(b"owned nested payload")
    definition_identity = timeline._identity(definition_stage, directory=False)
    bundle_identities = timeline._tree_identities(bundle_stage)
    timeline._freeze(definition_stage, bundle_stage)

    displaced_sources = tmp_path / "sources.bound-displaced"
    displaced_bundles = tmp_path / "bundles.bound-displaced"
    replacement_sources = tmp_path / "sources.replacement"
    replacement_bundles = tmp_path / "bundles.replacement"
    replacement_sources.mkdir()
    replacement_bundles.mkdir()
    foreign_definition = replacement_sources / definition_stage.name
    foreign_bundle = replacement_bundles / bundle_stage.name
    foreign_definition.write_bytes(b"foreign definition")
    foreign_bundle.mkdir()
    (foreign_bundle / "foreign-sentinel").write_bytes(b"foreign bundle")

    with timeline._bound_output_parents() as bindings:
        definition.parent.rename(displaced_sources)
        replacement_sources.rename(definition.parent)
        bundle.parent.rename(displaced_bundles)
        replacement_bundles.rename(bundle.parent)
        try:
            timeline._discard_definition_stage_bound(
                definition_stage, definition_identity, bindings
            )
            timeline._discard_bundle_stage_bound(
                bundle_stage, bundle_identities, bindings
            )
            assert not (displaced_sources / definition_stage.name).exists()
            assert not (displaced_bundles / bundle_stage.name).exists()
            assert (
                definition.parent / definition_stage.name
            ).read_bytes() == b"foreign definition"
            assert (
                bundle.parent / bundle_stage.name / "foreign-sentinel"
            ).read_bytes() == b"foreign bundle"
        finally:
            definition.parent.rename(replacement_sources)
            displaced_sources.rename(definition.parent)
            bundle.parent.rename(replacement_bundles)
            displaced_bundles.rename(bundle.parent)


def test_same_device_parent_swap_and_stage_rehome_during_wait_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    definition, bundle, lock = _set_output_paths(tmp_path, monkeypatch)
    _install_fast_publisher_gates(monkeypatch)
    displaced_sources = tmp_path / "sources.bound-displaced"
    displaced_bundles = tmp_path / "bundles.bound-displaced"
    replacement_sources = tmp_path / "sources.replacement"
    replacement_bundles = tmp_path / "bundles.replacement"
    replacement_sources.mkdir()
    replacement_bundles.mkdir()
    swapped = False

    def swap_and_rehome(_target: datetime) -> None:
        nonlocal swapped
        definition_stage = next(
            definition.parent.glob(f".{definition.name}.private-stage-*")
        )
        bundle_stage = next(bundle.parent.glob(f".{bundle.name}.private-stage-*"))
        definition.parent.rename(displaced_sources)
        replacement_sources.rename(definition.parent)
        bundle.parent.rename(displaced_bundles)
        replacement_bundles.rename(bundle.parent)
        swapped = True
        (displaced_sources / definition_stage.name).rename(
            definition.parent / definition_stage.name
        )
        displaced_bundle_stage = displaced_bundles / bundle_stage.name
        displaced_bundle_stage.chmod(0o755)
        displaced_bundle_stage.rename(bundle.parent / bundle_stage.name)

    monkeypatch.setattr(timeline, "_wait_until", swap_and_rehome)
    try:
        with pytest.raises(
            timeline.ConstructionTimelineV11Error, match="parent identity changed"
        ):
            timeline.publish_construction_timeline_v11(
                _future(), publication_authorized=True
            )
        assert swapped is True
        assert not definition.exists()
        assert not bundle.exists()
        assert not lock.exists()
    finally:
        if swapped:
            definition.parent.rename(replacement_sources)
            displaced_sources.rename(definition.parent)
            bundle.parent.rename(replacement_bundles)
            displaced_bundles.rename(bundle.parent)


def test_foreign_final_is_retained_and_not_rolled_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    definition, _bundle, _lock = _set_output_paths(tmp_path, monkeypatch)
    stage = definition.parent / ".definition.private-stage-test.json"
    stage.write_bytes(b"owned inode")
    stage.chmod(0o444)
    identity = timeline._identity(stage, directory=False)
    orphan = definition.parent / ".owned-published-orphan"

    with timeline._bound_output_parents() as bindings:
        timeline._promote_noreplace_checked(
            stage,
            definition,
            directory=False,
            parent_bindings=bindings,
        )
        definition.rename(orphan)
        definition.write_bytes(b"foreign final")
        error = timeline.ConstructionTimelineV11Error("injected later failure")
        still_published = timeline._rollback_definition_after_error(
            error,
            stage=stage,
            identity=identity,
            parent_bindings=bindings,
            may_have_left_stage=True,
        )

    assert still_published is True
    assert definition.read_bytes() == b"foreign final"
    assert timeline._has_identity(orphan, identity, directory=False)
    assert any("substituted" in note for note in error.__notes__)


@pytest.mark.parametrize("raise_after", ["bundle", "definition"])
def test_publisher_rolls_back_when_final_helper_raises_after_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raise_after: str
) -> None:
    definition, bundle, lock = _set_output_paths(tmp_path, monkeypatch)
    _install_fast_publisher_gates(monkeypatch)
    real_rename = timeline._rename_noreplace_at
    injected = False

    def success_then_raise(
        parent_descriptor: int, source_name: str, destination_name: str
    ) -> None:
        nonlocal injected
        real_rename(parent_descriptor, source_name, destination_name)
        target = bundle.name if raise_after == "bundle" else definition.name
        if not injected and destination_name == target:
            injected = True
            raise timeline.ConstructionTimelineV11Error(
                "injected final helper failure after successful promotion"
            )

    monkeypatch.setattr(timeline, "_rename_noreplace_at", success_then_raise)
    with pytest.raises(
        timeline.ConstructionTimelineV11Error,
        match="final helper failure after successful promotion",
    ):
        timeline.publish_construction_timeline_v11(
            _future(), publication_authorized=True
        )

    assert injected is True
    assert not definition.exists()
    assert not bundle.exists()
    assert not lock.exists()
    assert timeline._stage_paths() == []


@pytest.mark.parametrize("failure_point", ["completion", "result"])
def test_publisher_rolls_back_post_promotion_completion_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
) -> None:
    definition, bundle, lock = _set_output_paths(tmp_path, monkeypatch)
    _install_fast_publisher_gates(monkeypatch)
    injected = False

    if failure_point == "completion":
        real_assert = timeline._assert_parent_bindings

        def fail_completion(
            bindings: timeline.ParentBindings,
            *,
            label: str,
        ) -> None:
            nonlocal injected
            if label == "publication completion":
                injected = True
                raise timeline.ConstructionTimelineV11Error(
                    "injected post-promotion completion failure"
                )
            real_assert(bindings, label=label)

        monkeypatch.setattr(timeline, "_assert_parent_bindings", fail_completion)
    else:
        real_report = timeline._bundle_report

        def fail_result(path: Path) -> dict[str, dict[str, object]]:
            nonlocal injected
            if path == bundle:
                injected = True
                raise timeline.ConstructionTimelineV11Error(
                    "injected post-promotion result failure"
                )
            return real_report(path)

        monkeypatch.setattr(timeline, "_bundle_report", fail_result)

    with pytest.raises(
        timeline.ConstructionTimelineV11Error,
        match="injected post-promotion",
    ):
        timeline.publish_construction_timeline_v11(
            _future(),
            publication_authorized=True,
        )

    assert injected is True
    assert not definition.exists()
    assert not bundle.exists()
    assert not lock.exists()
    assert timeline._stage_paths() == []


def test_final_input_guard_failure_is_inside_lock_and_rollback_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    definition, bundle, lock = _set_output_paths(tmp_path, monkeypatch)
    accepted_guard = _install_fast_publisher_gates(monkeypatch)
    calls = 0

    def drift_only_at_final_guard() -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls <= 2:
            return accepted_guard
        return {"accepted-inputs": "drifted during final validation"}

    monkeypatch.setattr(timeline, "_input_guard_state", drift_only_at_final_guard)
    with pytest.raises(
        timeline.ConstructionTimelineV11Error,
        match="publication mutated accepted inputs",
    ):
        timeline.publish_construction_timeline_v11(
            _future(), publication_authorized=True
        )

    assert calls == 3
    assert not definition.exists()
    assert not bundle.exists()
    assert not lock.exists()
    assert timeline._stage_paths() == []
