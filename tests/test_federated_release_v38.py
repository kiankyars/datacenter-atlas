from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

try:
    from datacenter_atlas.datacenter_atlas import federation_v38 as core
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import federation_v38 as core


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode()


def _future(minutes: int = 10) -> str:
    target = datetime.now(UTC).replace(microsecond=0) + timedelta(minutes=minutes)
    return target.isoformat(timespec="seconds").replace("+00:00", "Z")


def _publisher_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, Path, Path, Path]:
    sources = tmp_path / "sources"
    indexes = tmp_path / "federated_indexes"
    sources.mkdir(parents=True)
    indexes.mkdir()
    definition = sources / core.DEFINITION.name
    index = indexes / core.INDEX_DIR.name
    lock = tmp_path / core.PUBLICATION_LOCK.name
    monkeypatch.setattr(core, "DEFINITION", definition)
    monkeypatch.setattr(core, "INDEX_DIR", index)
    monkeypatch.setattr(core, "PUBLICATION_LOCK", lock)
    return sources, indexes, definition, index, lock


def _install_fast_time_gates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(core, "_wait_until", lambda _target: None)
    monkeypatch.setattr(core, "_refresh_publication_ctimes", lambda *_args: None)
    monkeypatch.setattr(
        core, "_validate_publication_times", lambda *_args, **_kwargs: None
    )


def _remove_tree(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or path.is_file():
        path.chmod(0o600)
        path.unlink()
        return
    path.chmod(0o700)
    for child in path.rglob("*"):
        child.chmod(0o700 if child.is_dir() else 0o600)
    shutil.rmtree(path)


def _assert_no_residue(
    sources: Path,
    indexes: Path,
    definition: Path,
    index: Path,
    lock: Path,
) -> None:
    assert not definition.exists()
    assert not index.exists()
    assert not lock.exists()
    assert not list(sources.glob(f".{definition.name}.*.stage"))
    assert not list(indexes.glob(f".{index.name}.*"))


def test_v6_carrier_accepts_exact_governed_v97_and_rejects_closed_tampering() -> None:
    child = core._v97_child_definition()
    with pytest.raises(
        core.carrier_v5.FederatedReleaseError, match="manifest schema is invalid"
    ):
        core.carrier_v5._inspect_child(child)
    descriptor = core.federation._inspect_child(child)
    assert descriptor["counts"] == core.EXPECTED_OPEN_COUNTS
    assert descriptor["manifest"]["sha256"] == core.V97_MANIFEST_PIN[1]
    manifest = json.loads((core.V97_RELEASE / "manifest.json").read_text())
    contract = core.federation._governed_contract(manifest, label="test")
    assert contract["base_release"] == core.v96.RELEASE_ID

    missing = deepcopy(manifest)
    missing.pop("coordinate_boundary")
    with pytest.raises(
        core.federation.FederatedReleaseError, match="must be present together"
    ):
        core.federation._governed_contract(missing, label="test")

    tampered = deepcopy(manifest)
    tampered["public_release_delta"]["entities"] += 1
    with pytest.raises(core.federation.FederatedReleaseError, match="contract differs"):
        core.federation._governed_contract(tampered, label="test")

    open_delta = deepcopy(manifest)
    open_delta["internal_database_delta"]["unexpected"] = 1
    with pytest.raises(
        core.federation.FederatedReleaseError, match="schema is invalid"
    ):
        core.federation._governed_contract(open_delta, label="test")


def test_definition_replaces_only_v92_and_keeps_odbl_rows_byte_equal() -> None:
    generated_at = _future()
    accepted = json.loads(core.BASE_DEFINITION.read_text())
    current_raw = core.build_definition(generated_at)
    current = json.loads(current_raw)
    assert current_raw == _canonical(current)
    assert current["generated_at"] == generated_at
    current_by_id = {row["release_id"]: row for row in current["children"]}
    accepted_by_id = {row["release_id"]: row for row in accepted["children"]}
    assert set(current_by_id) == core.UNCHANGED_RELEASE_IDS | {core.NEW_RELEASE_ID}
    assert core.OLD_RELEASE_ID not in current_by_id
    for release_id in core.UNCHANGED_RELEASE_IDS:
        assert current_by_id[release_id] == accepted_by_id[release_id]
        assert _canonical(current_by_id[release_id]) == _canonical(
            accepted_by_id[release_id]
        )
    new = current_by_id[core.NEW_RELEASE_ID]
    assert new["expected_manifest_sha256"] == core.V97_MANIFEST_PIN[1]
    assert new["release_path"] == "../releases/2026-07-22-open-seed-v97"


def test_render_counts_rights_identity_and_policy_are_exact() -> None:
    definition = core.build_definition(_future())
    bundle = core.build_bundle(definition)
    accepted = json.loads(
        (core.BASE_INDEX_DIR / core.federation.INDEX_FILENAME).read_text()
    )
    index = bundle.index
    assert index["counts"] == core.EXPECTED_COUNTS
    assert {
        key: index["counts"][key] - accepted["counts"][key]
        for key in core.EXPECTED_DELTA
    } == core.EXPECTED_DELTA
    assert index["policy"] == core.federation.FEDERATION_POLICY
    assert index["policy"]["cross_source_deduplication"] is False
    assert index["policy"]["licenses_or_attributions_combined"] is False
    assert index["counts"]["unique_physical_sites"] is None
    by_id = {row["release_id"]: row for row in index["releases"]}
    accepted_by_id = {row["release_id"]: row for row in accepted["releases"]}
    for release_id in core.UNCHANGED_RELEASE_IDS:
        assert by_id[release_id] == accepted_by_id[release_id]
        assert "ODbL" in by_id[release_id]["rights"]["license_expression"]
    assert "ODbL" not in by_id[core.NEW_RELEASE_ID]["rights"]["license_expression"]
    assert by_id["osm-fuzzy-review-v2"]["scope"]["review_only"] is True


def test_real_prepublication_runs_two_replays_and_leaves_finals_absent() -> None:
    result = core.prepare_federation_v38(_future())
    assert result["status"] == "prepublication-validated"
    assert result["publication_authorized"] is False
    assert result["counts"] == core.EXPECTED_COUNTS
    assert result["delta_from_v37"] == core.EXPECTED_DELTA
    assert (
        result["bundle_files"][core.federation.MANIFEST_FILENAME]["sha256"]
        == result["two_replay_manifest_sha256"]
    )
    assert result["private_no_replace_roundtrip_validated"] is True
    assert result["final_definition_absent"] is True
    assert result["final_index_absent"] is True
    assert result["publication_lock_absent"] is True
    assert not core.DEFINITION.exists()
    assert not core.INDEX_DIR.exists()
    assert not core.PUBLICATION_LOCK.exists()


def test_authorization_partial_collision_and_replay_count_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(core.FederationV38Error, match="explicit authorization"):
        core.build_and_publish_federation_v38()
    with pytest.raises(core.FederationV38Error, match="exactly two"):
        core.prepare_federation_v38(_future(), replay_count=1)

    sources, indexes, definition, index, lock = _publisher_roots(tmp_path, monkeypatch)
    definition.write_text("collision")
    with pytest.raises(core.FederationV38Error, match="partial"):
        core.build_and_publish_federation_v38(_future(), publication_authorized=True)
    assert definition.read_text() == "collision"
    assert not index.exists()
    assert not lock.exists()
    assert not list(sources.glob(f".{definition.name}.*.stage"))
    assert not list(indexes.glob(f".{index.name}.*"))


def test_private_publisher_is_bundle_first_frozen_and_existing_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, indexes, definition, index, lock = _publisher_roots(tmp_path, monkeypatch)
    _install_fast_time_gates(monkeypatch)
    original = core._promote_noreplace
    final_promotions: list[Path] = []

    def observe(
        stage: Path,
        destination: Path,
        *,
        directory: bool,
        parent_bindings: core.ParentBindings | None = None,
    ) -> tuple[int, int]:
        if destination in {definition, index}:
            assert stage.parent == destination.parent
            final_promotions.append(destination)
        return original(
            stage,
            destination,
            directory=directory,
            parent_bindings=parent_bindings,
        )

    monkeypatch.setattr(core, "_promote_noreplace", observe)
    generated_at = _future()
    try:
        first = core.build_and_publish_federation_v38(
            generated_at, publication_authorized=True
        )
        second = core.build_and_publish_federation_v38(publication_authorized=True)
        assert first["status"] == "published"
        assert second["status"] == "existing-identical"
        assert first["generated_at"] == second["generated_at"] == generated_at
        assert first["counts"] == second["counts"] == core.EXPECTED_COUNTS
        assert final_promotions == [index, definition]
        with (
            core._publication_lock(),
            pytest.raises(core.FederationV38Error, match="active v38"),
        ):
            core.build_and_publish_federation_v38(publication_authorized=True)
        assert stat.S_IMODE(definition.stat().st_mode) == 0o444
        assert stat.S_IMODE(index.stat().st_mode) == 0o555
        assert all(
            stat.S_IMODE(path.stat().st_mode) == 0o444 for path in index.iterdir()
        )
        assert not lock.exists()
        assert not list(sources.glob(f".{definition.name}.*.stage"))
        assert not list(indexes.glob(f".{index.name}.*"))
    finally:
        _remove_tree(definition)
        _remove_tree(index)


def test_lock_and_stage_fstat_retry_then_persistent_failure_retains_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sources, indexes, _definition, index, lock = _publisher_roots(
        tmp_path, monkeypatch
    )
    original = core.os.fstat
    calls = 0

    def fail_once(descriptor: int) -> os.stat_result:
        nonlocal calls
        calls += 1
        metadata = original(descriptor)
        if calls == 1:
            raise OSError("one-shot fstat")
        return metadata

    monkeypatch.setattr(core.os, "fstat", fail_once)
    with core._publication_lock():
        assert lock.exists()
    assert calls == 2
    assert not lock.exists()

    def fail_directory(descriptor: int) -> os.stat_result:
        metadata = original(descriptor)
        if stat.S_ISDIR(metadata.st_mode):
            raise OSError("persistent directory fstat")
        return metadata

    monkeypatch.setattr(core.os, "fstat", fail_directory)
    with pytest.raises(core.FederationV38Error, match="identity unavailable") as error:
        core._create_owned_bundle_stage()
    retained = list(indexes.glob(f".{index.name}.*"))
    assert len(retained) == 1
    assert any("retained fail-closed" in note for note in error.value.__notes__)
    monkeypatch.setattr(core.os, "fstat", original)
    _remove_tree(retained[0])


def test_wait_slices_recursive_chronology_modes_bytes_and_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sleeps: list[float] = []
    wall_values = iter((100.0, 100.4, 100.8, 101.0))
    monkeypatch.setattr(core.time, "time", lambda: next(wall_values))
    monkeypatch.setattr(core.time, "sleep", sleeps.append)
    core._wait_until(datetime.fromtimestamp(101.0, tz=UTC))
    assert sleeps and all(0 < value <= 0.25 for value in sleeps)

    monkeypatch.undo()
    definition = tmp_path / "definition.json"
    definition.write_text("definition")
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    nested = bundle / "nested"
    nested.mkdir()
    member = nested / "member.json"
    member.write_text("member")
    core._freeze(definition, bundle)
    identities = core._tree_identities(bundle)
    definition_identity = core._identity(definition, directory=False)
    before = {path: path.read_bytes() for path in (definition, member)}
    target = datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=1)
    generated_at = target.isoformat(timespec="seconds").replace("+00:00", "Z")
    core._validate_publication_times(
        definition, bundle, generated_at=generated_at, require_live=False
    )
    core._wait_until(target)
    core._refresh_publication_ctimes(definition, bundle)
    core._validate_publication_times(
        definition, bundle, generated_at=generated_at, require_live=True
    )
    assert core._identity(definition, directory=False) == definition_identity
    core._assert_tree_identities(bundle, identities)
    assert {path: path.read_bytes() for path in before} == before
    assert stat.S_IMODE(definition.stat().st_mode) == 0o444
    assert stat.S_IMODE(bundle.stat().st_mode) == 0o555
    assert stat.S_IMODE(nested.stat().st_mode) == 0o555
    assert stat.S_IMODE(member.stat().st_mode) == 0o444
    _remove_tree(definition)
    _remove_tree(bundle)


def test_second_promotion_and_final_validation_failures_roll_back_exactly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, indexes, definition, index, lock = _publisher_roots(
        tmp_path / "second", monkeypatch
    )
    _install_fast_time_gates(monkeypatch)
    original = core._promote_noreplace

    def fail_definition(
        stage: Path,
        destination: Path,
        *,
        directory: bool,
        parent_bindings: core.ParentBindings | None = None,
    ) -> tuple[int, int]:
        if destination == definition:
            raise core.FederationV38Error("definition promotion failure")
        return original(
            stage,
            destination,
            directory=directory,
            parent_bindings=parent_bindings,
        )

    monkeypatch.setattr(core, "_promote_noreplace", fail_definition)
    with pytest.raises(core.FederationV38Error, match="definition promotion"):
        core.build_and_publish_federation_v38(_future(), publication_authorized=True)
    _assert_no_residue(sources, indexes, definition, index, lock)

    monkeypatch.setattr(core, "_promote_noreplace", original)
    monkeypatch.setattr(
        core,
        "validate_federation_v38",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            core.FederationV38Error("injected final validation failure")
        ),
    )
    with pytest.raises(core.FederationV38Error, match="injected final validation"):
        core.build_and_publish_federation_v38(_future(), publication_authorized=True)
    _assert_no_residue(sources, indexes, definition, index, lock)


def test_parent_swap_with_stage_inode_rehoming_cannot_redirect_finals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, indexes, definition, index, lock = _publisher_roots(tmp_path, monkeypatch)
    _install_fast_time_gates(monkeypatch)
    displaced_sources = tmp_path / "bound-sources-parent"
    displaced_indexes = tmp_path / "bound-indexes-parent"
    swapped = False

    def swap_parents_and_rehome_owned_stages(_target: datetime) -> None:
        nonlocal swapped
        sources.rename(displaced_sources)
        sources.mkdir()
        definition_stage = next(displaced_sources.glob(f".{definition.name}.*.stage"))
        definition_stage.rename(sources / definition_stage.name)

        indexes.rename(displaced_indexes)
        indexes.mkdir()
        bundle_stage = next(displaced_indexes.glob(f".{index.name}.*"))
        bundle_stage.chmod(0o755)
        bundle_stage.rename(indexes / bundle_stage.name)
        (indexes / bundle_stage.name).chmod(0o555)
        swapped = True

    monkeypatch.setattr(core, "_wait_until", swap_parents_and_rehome_owned_stages)
    try:
        with pytest.raises(core.FederationV38Error, match="parent identity changed"):
            core.build_and_publish_federation_v38(
                _future(), publication_authorized=True
            )
        assert swapped is True
        _assert_no_residue(sources, indexes, definition, index, lock)
        assert not list(sources.iterdir())
        assert not list(indexes.iterdir())
    finally:
        if sources.exists():
            _remove_tree(sources)
        if indexes.exists():
            _remove_tree(indexes)
        if displaced_sources.exists():
            displaced_sources.rename(sources)
        if displaced_indexes.exists():
            displaced_indexes.rename(indexes)


def test_dirfd_bound_promotion_cannot_be_redirected_by_in_syscall_parent_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, indexes, definition, index, lock = _publisher_roots(tmp_path, monkeypatch)
    _install_fast_time_gates(monkeypatch)
    displaced_sources = tmp_path / "bound-sources-parent"
    displaced_indexes = tmp_path / "bound-indexes-parent"
    original = core._rename_bound_noreplace
    foreign_definition = b"foreign definition retained\n"
    foreign_index = b"foreign index retained\n"
    owned_identities: set[tuple[int, int]] = set()
    attacked = False

    def attack_inside_bound_rename(
        binding: tuple[Path, tuple[int, int], int],
        source_name: str,
        destination_name: str,
    ) -> None:
        nonlocal attacked
        if destination_name == index.name and not attacked:
            definition_stage = next(sources.glob(f".{definition.name}.*.stage"))
            bundle_stage = next(indexes.glob(f".{index.name}.*"))
            owned_identities.update(
                {
                    core._identity(definition_stage, directory=False),
                    core._identity(bundle_stage, directory=True),
                }
            )

            sources.rename(displaced_sources)
            sources.mkdir()
            definition_stage = displaced_sources / definition_stage.name
            definition_stage.rename(sources / definition_stage.name)

            indexes.rename(displaced_indexes)
            indexes.mkdir()
            bundle_stage = displaced_indexes / bundle_stage.name
            bundle_stage.chmod(0o755)
            bundle_stage.rename(indexes / bundle_stage.name)
            (indexes / bundle_stage.name).chmod(0o555)

            definition.write_bytes(foreign_definition)
            index.mkdir()
            (index / "foreign.txt").write_bytes(foreign_index)
            attacked = True
        original(binding, source_name, destination_name)

    monkeypatch.setattr(core, "_rename_bound_noreplace", attack_inside_bound_rename)
    try:
        with pytest.raises(core.FederationV38Error, match="parent identity changed"):
            core.build_and_publish_federation_v38(
                _future(), publication_authorized=True
            )
        assert attacked is True
        assert definition.read_bytes() == foreign_definition
        assert (index / "foreign.txt").read_bytes() == foreign_index
        assert core._identity(definition, directory=False) not in owned_identities
        assert core._identity(index, directory=True) not in owned_identities
        assert not (displaced_sources / definition.name).exists()
        assert not (displaced_indexes / index.name).exists()
        assert not list(sources.glob(f".{definition.name}.*.stage"))
        assert not list(indexes.glob(f".{index.name}.*"))
        assert not lock.exists()
    finally:
        if sources.exists():
            _remove_tree(sources)
        if indexes.exists():
            _remove_tree(indexes)
        if displaced_sources.exists():
            displaced_sources.rename(sources)
        if displaced_indexes.exists():
            displaced_indexes.rename(indexes)


def test_bound_cleanup_removes_no_rehome_stages_after_in_promotion_parent_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, indexes, definition, index, lock = _publisher_roots(tmp_path, monkeypatch)
    _install_fast_time_gates(monkeypatch)
    displaced_sources = tmp_path / "bound-sources-parent"
    displaced_indexes = tmp_path / "bound-indexes-parent"
    original = core._rename_bound_noreplace
    source_sentinel = b"replacement source parent untouched\n"
    index_sentinel = b"replacement index parent untouched\n"
    stage_names: dict[str, str] = {}
    attacked = False

    def swap_without_rehome_inside_bound_rename(
        binding: tuple[Path, tuple[int, int], int],
        source_name: str,
        destination_name: str,
    ) -> None:
        nonlocal attacked
        if destination_name == index.name and not attacked:
            definition_stage = next(sources.glob(f".{definition.name}.*.stage"))
            bundle_stage = next(indexes.glob(f".{index.name}.*"))
            stage_names.update(
                definition=definition_stage.name,
                bundle=bundle_stage.name,
            )
            sources.rename(displaced_sources)
            sources.mkdir()
            (sources / "foreign.keep").write_bytes(source_sentinel)
            indexes.rename(displaced_indexes)
            indexes.mkdir()
            (indexes / "foreign.keep").write_bytes(index_sentinel)
            attacked = True
        original(binding, source_name, destination_name)

    monkeypatch.setattr(
        core, "_rename_bound_noreplace", swap_without_rehome_inside_bound_rename
    )
    try:
        with pytest.raises(core.FederationV38Error, match="parent identity changed"):
            core.build_and_publish_federation_v38(
                _future(), publication_authorized=True
            )
        assert attacked is True
        assert (sources / "foreign.keep").read_bytes() == source_sentinel
        assert (indexes / "foreign.keep").read_bytes() == index_sentinel
        assert not definition.exists()
        assert not index.exists()
        assert not (displaced_sources / definition.name).exists()
        assert not (displaced_indexes / index.name).exists()
        assert not (displaced_sources / stage_names["definition"]).exists()
        assert not (displaced_indexes / stage_names["bundle"]).exists()
        assert not lock.exists()
    finally:
        if sources.exists():
            _remove_tree(sources)
        if indexes.exists():
            _remove_tree(indexes)
        if displaced_sources.exists():
            displaced_sources.rename(sources)
        if displaced_indexes.exists():
            displaced_indexes.rename(indexes)


def test_current_parent_file_cleanup_preserves_post_assertion_substitution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, _indexes, definition, _index, _lock = _publisher_roots(
        tmp_path, monkeypatch
    )
    displaced_parent = tmp_path / "bound-sources-parent"
    owned_payload = b"owned definition stage\n"
    foreign_payload = b"foreign replacement definition stage\n"
    with core._bound_parent_bindings() as parent_bindings:
        stage, identity = core._create_owned_definition_stage(owned_payload)
        sources.rename(displaced_parent)
        sources.mkdir()
        stage = displaced_parent / stage.name
        stage.rename(sources / stage.name)
        stage = sources / stage.name
        owned_displaced = sources / f"{stage.name}.owned-displaced"
        original = core._has_bound_identity
        foreign_identity: tuple[int, int] | None = None
        injected = False

        def substitute_after_assertion(
            binding: tuple[Path, tuple[int, int], int],
            name: str,
            expected_identity: tuple[int, int],
            *,
            directory: bool,
        ) -> bool:
            nonlocal foreign_identity, injected
            result = original(
                binding,
                name,
                expected_identity,
                directory=directory,
            )
            if result and name == stage.name and not directory and not injected:
                stage.rename(owned_displaced)
                stage.write_bytes(foreign_payload)
                foreign_identity = core._identity(stage, directory=False)
                injected = True
            return result

        monkeypatch.setattr(core, "_has_bound_identity", substitute_after_assertion)
        operation_error = core.FederationV38Error("injected operation failure")
        core._cleanup_private_stages(
            definition=stage,
            definition_identity=identity,
            bundle=None,
            bundle_identities=None,
            parent_bindings=parent_bindings,
            active_error=operation_error,
        )
        assert injected is True
        assert stage.read_bytes() == foreign_payload
        assert core._identity(stage, directory=False) == foreign_identity
        assert owned_displaced.read_bytes() == owned_payload
        assert core._identity(owned_displaced, directory=False) == identity
        assert any("cleanup failed" in note for note in operation_error.__notes__)
        assert not definition.exists()
        _remove_tree(stage)
        _remove_tree(owned_displaced)
        sources.rmdir()
        displaced_parent.rename(sources)


def test_current_parent_bundle_cleanup_preserves_post_assertion_substitution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sources, indexes, _definition, index, _lock = _publisher_roots(
        tmp_path, monkeypatch
    )
    displaced_parent = tmp_path / "bound-indexes-parent"
    owned_payload = b"owned bundle member\n"
    foreign_payload = b"foreign replacement bundle member\n"
    with core._bound_parent_bindings() as parent_bindings:
        stage, identities = core._create_owned_bundle_stage()
        core._write_new_file(
            stage / "owned.txt",
            owned_payload,
            identity_tracker=identities,
            tracker_key="owned.txt",
        )
        indexes.rename(displaced_parent)
        indexes.mkdir()
        stage = displaced_parent / stage.name
        stage.rename(indexes / stage.name)
        stage = indexes / stage.name
        owned_displaced = indexes / f"{stage.name}.owned-displaced"
        original = core._assert_bound_tree_identities
        foreign_root_identity: tuple[int, int] | None = None
        foreign_member_identity: tuple[int, int] | None = None
        injected = False

        def substitute_after_assertion(
            binding: tuple[Path, tuple[int, int], int],
            root_name: str,
            expected: object,
        ) -> None:
            nonlocal foreign_member_identity, foreign_root_identity, injected
            original(binding, root_name, expected)
            if root_name == stage.name and not injected:
                stage.rename(owned_displaced)
                stage.mkdir()
                foreign_member = stage / "foreign.txt"
                foreign_member.write_bytes(foreign_payload)
                foreign_root_identity = core._identity(stage, directory=True)
                foreign_member_identity = core._identity(
                    foreign_member, directory=False
                )
                injected = True

        monkeypatch.setattr(
            core, "_assert_bound_tree_identities", substitute_after_assertion
        )
        operation_error = core.FederationV38Error("injected operation failure")
        core._cleanup_private_stages(
            definition=None,
            definition_identity=None,
            bundle=stage,
            bundle_identities=identities,
            parent_bindings=parent_bindings,
            active_error=operation_error,
        )
        assert injected is True
        assert (stage / "foreign.txt").read_bytes() == foreign_payload
        assert core._identity(stage, directory=True) == foreign_root_identity
        assert (
            core._identity(stage / "foreign.txt", directory=False)
            == foreign_member_identity
        )
        assert (owned_displaced / "owned.txt").read_bytes() == owned_payload
        assert core._tree_identities(owned_displaced) == identities
        assert any("cleanup failed" in note for note in operation_error.__notes__)
        assert not index.exists()
        _remove_tree(stage)
        _remove_tree(owned_displaced)
        indexes.rmdir()
        displaced_parent.rename(indexes)


def test_guard_drift_after_final_validate_rolls_back_both_finals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, indexes, definition, index, lock = _publisher_roots(tmp_path, monkeypatch)
    _install_fast_time_gates(monkeypatch)
    original_guard = core._guard_state
    original_validate = core.validate_federation_v38
    activated = False

    def activate_drift(*args: object, **kwargs: object) -> object:
        nonlocal activated
        result = original_validate(*args, **kwargs)
        activated = True
        return result

    def drifting_guard() -> dict[str, object]:
        state = original_guard()
        if activated:
            state["carrier"] = (state["carrier"][0], "0" * 64)
        return state

    monkeypatch.setattr(core, "validate_federation_v38", activate_drift)
    monkeypatch.setattr(core, "_guard_state", drifting_guard)
    with pytest.raises(core.FederationV38Error, match="mutated accepted inputs"):
        core.build_and_publish_federation_v38(_future(), publication_authorized=True)
    assert activated is True
    _assert_no_residue(sources, indexes, definition, index, lock)


@pytest.mark.parametrize("substituted", ["bundle", "definition"])
def test_substituted_published_inode_is_retained_with_rollback_notes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    substituted: str,
) -> None:
    _sources, _indexes, definition, index, lock = _publisher_roots(
        tmp_path, monkeypatch
    )
    _install_fast_time_gates(monkeypatch)
    displaced = tmp_path / f"displaced-{substituted}"
    foreign = b"foreign inode retained\n"

    def substitute_then_fail(*_args: object, **_kwargs: object) -> dict[str, object]:
        target = index if substituted == "bundle" else definition
        if substituted == "bundle":
            target.chmod(0o755)
        target.rename(displaced)
        if substituted == "bundle":
            target.mkdir()
            (target / "foreign.txt").write_bytes(foreign)
        else:
            target.write_bytes(foreign)
        raise core.FederationV38Error(f"injected substituted {substituted}")

    monkeypatch.setattr(core, "validate_federation_v38", substitute_then_fail)
    with pytest.raises(
        core.FederationV38Error, match=f"injected substituted {substituted}"
    ) as error:
        core.build_and_publish_federation_v38(_future(), publication_authorized=True)
    notes = getattr(error.value, "__notes__", [])
    assert any("substituted v38" in note for note in notes)
    assert displaced.exists()
    if substituted == "bundle":
        assert index.is_dir()
        assert (index / "foreign.txt").read_bytes() == foreign
        assert not definition.exists()
    else:
        assert definition.read_bytes() == foreign
        assert not index.exists()
    assert not lock.exists()
    for path in (displaced, definition, index):
        _remove_tree(path)


def test_carrier_source_and_accepted_inputs_are_exactly_pinned() -> None:
    core._validate_guard(core._guard_state())
    assert (
        core.CARRIER_SOURCE.stat().st_size,
        hashlib.sha256(core.CARRIER_SOURCE.read_bytes()).hexdigest(),
    ) == core.CARRIER_SOURCE_PIN
    assert stat.S_IMODE(core.CARRIER_SOURCE.stat().st_mode) == 0o644
    assert not core.DEFINITION.exists()
    assert not core.INDEX_DIR.exists()
    assert not core.PUBLICATION_LOCK.exists()


def test_prepare_runner_rejects_publication_flag_without_touching_finals() -> None:
    runner = core.ROOT / "scripts/prepare_federation_v38.py"
    completed = subprocess.run(
        [sys.executable, str(runner), "--publish-authorized"],
        cwd=core.ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 2
    assert "unrecognized arguments: --publish-authorized" in completed.stderr
    assert not core.DEFINITION.exists()
    assert not core.INDEX_DIR.exists()
    assert not core.PUBLICATION_LOCK.exists()
    assert not list(core.DEFINITION.parent.glob(f".{core.DEFINITION.name}.*.stage"))
    assert not list(core.INDEX_DIR.parent.glob(f".{core.INDEX_DIR.name}.*"))
