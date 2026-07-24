from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile

import pytest

try:
    from datacenter_atlas.datacenter_atlas import open_seed_v97 as core
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import open_seed_v97 as core


def _future(minutes: int = 10) -> tuple[datetime, str]:
    target = datetime.now(UTC).replace(microsecond=0) + timedelta(minutes=minutes)
    return target, target.isoformat(timespec="seconds").replace("+00:00", "Z")


def _planned() -> tuple[dict[str, object], list[dict[str, str]], list[Path]]:
    base = core._validate_base()
    wall = core.v95.v70.parse_utc("2099-01-01T00:00:00Z", label="test wall")
    selected, paths = core.selected_inputs(
        base,
        recorded_at="2099-01-01T00:00:00Z",
        validation_wall_clock=wall,
    )
    return base, selected, paths


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _publisher_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, Path, Path, Path]:
    sources = tmp_path / "sources"
    releases = tmp_path / "releases"
    sources.mkdir()
    releases.mkdir()
    definition = sources / core.DEFINITION.name
    release = releases / core.RELEASE.name
    lock = tmp_path / core.PUBLICATION_LOCK.name
    monkeypatch.setattr(core, "DEFINITION", definition)
    monkeypatch.setattr(core, "RELEASE", release)
    monkeypatch.setattr(core, "PUBLICATION_LOCK", lock)
    return sources, releases, definition, release, lock


def _install_fast_publication_gates(monkeypatch: pytest.MonkeyPatch) -> None:
    def validate(
        definition_path: Path,
        release_path: Path,
        **_kwargs: object,
    ) -> dict[str, object]:
        definition = json.loads(definition_path.read_text())
        manifest = core._validate_release_facts(
            release_path, recorded_at=definition["build"]["recorded_at"]
        )
        return {
            **manifest,
            "two_replay_manifest_sha256": core._sha256(
                (release_path / "manifest.json").read_bytes()
            ),
        }

    monkeypatch.setattr(core, "validate_staged_open_seed_v97", validate)
    monkeypatch.setattr(core, "validate_open_seed_v97", validate)
    monkeypatch.setattr(core, "_wait_until", lambda _target: None)
    monkeypatch.setattr(core, "_refresh_publication_ctimes", lambda *_args: None)
    monkeypatch.setattr(
        core, "_validate_publication_times", lambda *_args, **_kwargs: None
    )


def _assert_no_publisher_residue(
    sources: Path, releases: Path, definition: Path, release: Path, lock: Path
) -> None:
    assert not definition.exists()
    assert not release.exists()
    assert not lock.exists()
    assert not list(sources.glob(f".{definition.name}.*.stage"))
    assert not list(releases.glob(f".{release.name}.*"))


def _remove_test_tree(path: Path) -> None:
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


def test_exact_v96_base_and_accepted_artifacts_are_ready() -> None:
    guard = core._guard_state()
    core._validate_guard(guard)
    report = core.readiness_report()
    assert report["status"] == "ready"
    assert report["base_release_id"] == core.v96.RELEASE_ID
    assert report["base_definition_sha256"] == core.BASE_DEFINITION_PIN[1]
    assert report["base_tree_sha256"] == core.BASE_TREE_SHA256
    assert report["accepted_artifacts_validated"] == ["ctrls", "edgeconnex_lambda"]
    assert report["planned_input_count"] == 519
    assert report["stale_status_suppression_unchanged"] == sorted(
        core.v96.EXPECTED_STALE_PROJECT_KEYS
    )
    assert report["final_definition_absent"] is True
    assert report["final_release_absent"] is True
    assert report["publication_lock_absent"] is True


def test_selection_is_exact_append_and_preserves_all_516_v96_rows() -> None:
    base, selected, paths = _planned()
    rows = base["curated_inputs"]
    assert isinstance(rows, list)
    assert len(selected) == len(paths) == 519
    assert selected[: core.BASE_INPUT_COUNT] == rows
    assert [row["path"] for row in selected[core.BASE_INPUT_COUNT :]] == list(
        core.APPEND_ORDER
    )
    assert [row["sha256"] for row in selected[core.BASE_INPUT_COUNT :]] == [
        core.SOURCE_PINS[path][1] for path in core.APPEND_ORDER
    ]
    assert len({row["path"] for row in selected}) == 519


def test_source_contract_keeps_ctrls_untyped_and_edge_23mw_unnormalized() -> None:
    documents = core._validate_accepted_inputs()
    contract = core._validate_source_claims(documents)
    assert contract["stable_keys"] == core.ADDED_ENTITY_KEYS
    assert contract["evidence_keys"] == core.EXPECTED_EVIDENCE_KEYS
    assert contract["lifecycle"] == core.EXPECTED_LIFECYCLE
    assert contract["workloads"] == core.EXPECTED_WORKLOADS
    assert all(not documents[path]["capacities"] for path in core.APPEND_ORDER)
    assert all(not documents[path]["operating_models"] for path in core.APPEND_ORDER)
    assert all(not documents[path]["workloads"] for path in core.APPEND_ORDER[:2])
    assert all(
        documents[path][entity]["coordinates"] is None
        and documents[path][entity]["geometry"] is None
        for path in core.APPEND_ORDER
        for entity in ("campus", "project")
    )


def test_real_database_renderer_and_byte_frozen_v96_projection() -> None:
    base, _selected, paths = _planned()
    with tempfile.TemporaryDirectory(
        prefix="open-seed-v97-render-test-", dir="/private/tmp"
    ) as temporary:
        root = Path(temporary)
        connection = core._build_database(
            base,
            paths,
            root / "atlas.sqlite",
            recorded_at="2099-01-01T00:00:00Z",
        )
        try:
            counts = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in core.EXPECTED_DATABASE_COUNTS
            }
            assert counts == core.EXPECTED_DATABASE_COUNTS
            release = root / "release"
            core._write_release(connection, release, recorded_at="2099-01-01T00:00:00Z")
        finally:
            connection.close()
        manifest = core._validate_release_facts(
            release, recorded_at="2099-01-01T00:00:00Z"
        )
        assert {
            key: manifest[key]
            for key in (
                "entities",
                "evidence_records",
                "lifecycle_freshness_records",
                "capacity_estimates",
                "construction_pipeline_records",
                "construction_source_signals",
            )
        } == {
            "entities": 1_053,
            "evidence_records": 693,
            "lifecycle_freshness_records": 583,
            "capacity_estimates": 570,
            "construction_pipeline_records": 531,
            "construction_source_signals": 432,
        }
        assert manifest["base_rows_frozen"] is True
        assert manifest["governed_base_row_replacements"] == {}
        expectations = {
            "entities.csv": ("stable_key", core.ADDED_ENTITY_KEYS),
            "evidence.csv": ("evidence_id", core.PUBLIC_EVIDENCE_IDS),
            "lifecycle_freshness.csv": ("stable_key", core.ADDED_PROJECT_KEYS),
            "construction_pipeline.csv": ("stable_key", core.ADDED_PROJECT_KEYS),
            "construction_source_signals.csv": (
                "source_observation_evidence_id",
                core.PUBLIC_EVIDENCE_IDS,
            ),
        }
        for filename, (key, additions) in expectations.items():
            before = {row[key]: row for row in _rows(core.BASE_RELEASE / filename)}
            after = {row[key]: row for row in _rows(release / filename)}
            assert not set(before) - set(after)
            assert set(after) - set(before) == set(additions)
            assert all(after[row_key] == row for row_key, row in before.items())
        assert (release / "capacity_estimates.csv").read_bytes() == (
            core.BASE_RELEASE / "capacity_estimates.csv"
        ).read_bytes()
        for filename in ("resolution_candidates.csv", "resolution_candidates.json"):
            assert (release / filename).read_bytes() == (
                core.BASE_RELEASE / filename
            ).read_bytes()
        assert (
            len(json.loads((release / "source_inputs.json").read_text())["sources"])
            == 620
        )


def test_full_prepublication_runs_two_replays_and_leaves_no_final() -> None:
    result = core.prepare_open_seed_v97()
    assert result["status"] == "prepublication-validated"
    assert result["publication_authorized"] is False
    assert result["planned_input_count"] == 519
    assert result["manifest_sha256"] == result["two_replay_manifest_sha256"]
    assert result["entities"] == 1_053
    assert result["internal_evidence_records"] == 889
    assert result["evidence_records"] == 693
    assert result["source_input_rows"] == 620
    assert result["private_no_replace_roundtrip_validated"] is True
    assert result["final_definition_absent"] is True
    assert result["final_release_absent"] is True
    assert result["publication_lock_absent"] is True
    assert not core.DEFINITION.exists()
    assert not core.RELEASE.exists()
    assert not core.PUBLICATION_LOCK.exists()


def test_publication_requires_authorization_and_exactly_two_replays() -> None:
    with pytest.raises(core.OpenSeedV97Error, match="requires explicit"):
        core.build_open_seed_v97()
    with pytest.raises(core.OpenSeedV97Error, match="exactly two"):
        core.prepare_open_seed_v97(replay_count=1)
    assert not core.DEFINITION.exists()
    assert not core.RELEASE.exists()
    assert not core.PUBLICATION_LOCK.exists()


def test_private_publisher_is_release_first_and_existing_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, releases, definition, release, lock = _publisher_roots(
        tmp_path, monkeypatch
    )
    _install_fast_publication_gates(monkeypatch)
    original = core._promote_noreplace
    promotions: list[Path] = []

    def observe(stage: Path, destination: Path, *, directory: bool) -> tuple[int, int]:
        assert Path(stage).parent == Path(destination).parent
        promotions.append(Path(destination))
        return original(stage, destination, directory=directory)

    monkeypatch.setattr(core, "_promote_noreplace", observe)
    _wall, recorded_at = _future()
    try:
        first = core.build_open_seed_v97(
            recorded_at=recorded_at, publication_authorized=True
        )
        second = core.build_open_seed_v97(publication_authorized=True)
        assert first["status"] == "published"
        assert second["status"] == "existing-identical"
        assert first["recorded_at"] == second["recorded_at"] == recorded_at
        assert first["manifest_sha256"] == second["manifest_sha256"]
        assert promotions == [release, definition]
        assert stat.S_IMODE(definition.stat().st_mode) == 0o444
        assert stat.S_IMODE(release.stat().st_mode) == 0o555
        assert all(
            stat.S_IMODE(path.stat().st_mode) == 0o444 for path in release.iterdir()
        )
        assert not lock.exists()
        assert not list(sources.glob(f".{definition.name}.*.stage"))
        assert not list(releases.glob(f".{release.name}.*"))
    finally:
        core._thaw_private_stage(definition, release)


@pytest.mark.parametrize("collision", ["definition", "release"])
def test_partial_final_collision_fails_before_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, collision: str
) -> None:
    sources, releases, definition, release, lock = _publisher_roots(
        tmp_path, monkeypatch
    )
    definition.write_text("collision") if collision == "definition" else release.mkdir()
    _wall, recorded_at = _future()
    with pytest.raises(core.OpenSeedV97Error, match="partial"):
        core.build_open_seed_v97(recorded_at=recorded_at, publication_authorized=True)
    assert not lock.exists()
    assert not list(sources.glob(f".{definition.name}.*.stage"))
    assert not list(releases.glob(f".{release.name}.*"))


def test_lock_fstat_one_shot_retries_and_persistent_failure_retains_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sources, _releases, _definition, _release, lock = _publisher_roots(
        tmp_path, monkeypatch
    )
    original = core.os.fstat
    calls = 0

    def fail_once(descriptor: int) -> os.stat_result:
        nonlocal calls
        calls += 1
        metadata = original(descriptor)
        if calls == 1:
            raise OSError("one-shot lock fstat")
        return metadata

    monkeypatch.setattr(core.os, "fstat", fail_once)
    with core._publication_lock():
        assert lock.exists()
    assert calls == 2
    assert not lock.exists()

    calls = 0

    def fail_always(descriptor: int) -> os.stat_result:
        nonlocal calls
        calls += 1
        original(descriptor)
        raise OSError("persistent lock fstat")

    monkeypatch.setattr(core.os, "fstat", fail_always)
    with pytest.raises(core.OpenSeedV97Error, match="identity unavailable"):
        with core._publication_lock():
            pytest.fail("persistent identity failure must not enter lock body")
    assert calls == 2
    assert lock.exists()
    lock.unlink()


def test_release_root_fstat_retry_and_persistent_failure_is_not_adopted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sources, releases, _definition, release, lock = _publisher_roots(
        tmp_path, monkeypatch
    )
    original = core.os.fstat
    directory_failures = 0

    def fail_directory_once(descriptor: int) -> os.stat_result:
        nonlocal directory_failures
        metadata = original(descriptor)
        if stat.S_ISDIR(metadata.st_mode) and directory_failures == 0:
            directory_failures += 1
            raise OSError("one-shot root fstat")
        return metadata

    monkeypatch.setattr(core.os, "fstat", fail_directory_once)
    stage, identities = core._create_owned_release_stage()
    assert directory_failures == 1
    assert identities == core._tree_identities(stage)
    core._discard_release_stage(stage, identities)

    def fail_directory_always(descriptor: int) -> os.stat_result:
        metadata = original(descriptor)
        if stat.S_ISDIR(metadata.st_mode):
            raise OSError("persistent root fstat")
        return metadata

    monkeypatch.setattr(core.os, "fstat", fail_directory_always)
    with pytest.raises(core.OpenSeedV97Error, match="identity unavailable") as error:
        with core._publication_lock():
            core._create_owned_release_stage()
    retained = list(releases.glob(f".{release.name}.*"))
    assert len(retained) == 1
    assert any("retained fail-closed" in note for note in error.value.__notes__)
    assert not lock.exists()
    monkeypatch.setattr(core.os, "fstat", original)
    _remove_test_tree(retained[0])


@pytest.mark.parametrize("persistent", [False, True])
def test_definition_fstat_retry_never_adopts_unknown_inode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, persistent: bool
) -> None:
    sources, releases, definition, release, lock = _publisher_roots(
        tmp_path, monkeypatch
    )
    original = core.os.fstat
    regular_calls = 0
    definition_failures = 0

    def injected(descriptor: int) -> os.stat_result:
        nonlocal regular_calls, definition_failures
        metadata = original(descriptor)
        if stat.S_ISREG(metadata.st_mode):
            regular_calls += 1
            if regular_calls >= 2 and (persistent or definition_failures == 0):
                definition_failures += 1
                raise OSError("definition fstat failure")
        return metadata

    monkeypatch.setattr(core.os, "fstat", injected)
    _wall, recorded_at = _future()
    if not persistent:
        monkeypatch.setattr(
            core,
            "_build_database",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                core.OpenSeedV97Error("stop after identity retry")
            ),
        )
        with pytest.raises(core.OpenSeedV97Error, match="stop after identity"):
            core.build_open_seed_v97(
                recorded_at=recorded_at, publication_authorized=True
            )
        assert definition_failures == 1
        _assert_no_publisher_residue(sources, releases, definition, release, lock)
    else:
        with pytest.raises(core.OpenSeedV97Error, match="identity unavailable"):
            core.build_open_seed_v97(
                recorded_at=recorded_at, publication_authorized=True
            )
        retained = list(sources.glob(f".{definition.name}.*.stage"))
        assert len(retained) == 1
        assert not list(releases.glob(f".{release.name}.*"))
        assert not lock.exists()
        _remove_test_tree(retained[0])


def test_root_definition_and_descendant_substitution_are_retained_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cases = ("root", "definition", "descendant")
    for index, case in enumerate(cases):
        case_root = tmp_path / str(index)
        case_root.mkdir()
        sources, releases, definition, release, lock = _publisher_roots(
            case_root, monkeypatch
        )
        original = core._fstat_identity_with_retry
        displaced: list[Path] = []
        injected = False

        def substitute(
            descriptor: int,
            *,
            expected_kind: str,
            label: str,
            expected_mode: int | None = None,
            attempts: int = 2,
        ) -> tuple[int, int, str]:
            nonlocal injected
            result = original(
                descriptor,
                expected_kind=expected_kind,
                label=label,
                expected_mode=expected_mode,
                attempts=attempts,
            )
            matches = {
                "root": label == "v97 release stage root",
                "definition": label == "v97 definition stage",
                "descendant": label.startswith("v97 release member "),
            }
            if matches[case] and not injected:
                injected = True
                if case == "root":
                    target = next(releases.glob(f".{release.name}.*"))
                elif case == "definition":
                    target = next(sources.glob(f".{definition.name}.*.stage"))
                else:
                    release_stage = next(releases.glob(f".{release.name}.*"))
                    filename = label.removeprefix("v97 release member ")
                    target = release_stage / filename
                moved = target.with_name(target.name + ".displaced")
                target.rename(moved)
                if expected_kind == "directory":
                    target.mkdir()
                else:
                    target.write_text("foreign")
                displaced.append(moved)
            return result

        monkeypatch.setattr(core, "_fstat_identity_with_retry", substitute)
        _wall, recorded_at = _future()
        with pytest.raises(core.OpenSeedV97Error):
            core.build_open_seed_v97(
                recorded_at=recorded_at, publication_authorized=True
            )
        assert injected is True
        assert displaced
        assert not lock.exists()
        assert not definition.exists()
        assert not release.exists()
        for path in [*sources.iterdir(), *releases.iterdir()]:
            _remove_test_tree(path)
        monkeypatch.setattr(core, "_fstat_identity_with_retry", original)


def test_wait_slices_and_nested_recursive_publication_chronology(
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
    release = tmp_path / "release"
    release.mkdir()
    nested = release / "nested"
    nested.mkdir()
    member = nested / "member.json"
    member.write_text("member")
    core._freeze(definition, release)
    release_identities = core._tree_identities(release)
    definition_identity = core._identity(definition, directory=False)
    before = {path: path.read_bytes() for path in (definition, member)}
    target = datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=1)
    recorded_at = target.isoformat(timespec="seconds").replace("+00:00", "Z")
    paths = (definition, release, nested, member)
    for path in paths:
        metadata = path.stat(follow_symlinks=False)
        birth = getattr(metadata, "st_birthtime", metadata.st_mtime)
        assert max(birth, metadata.st_mtime) <= target.timestamp() + 1e-6
    core._validate_publication_times(
        definition,
        release,
        recorded_at=recorded_at,
        require_live=False,
    )
    core._wait_until(target)
    core._refresh_publication_ctimes(definition, release)
    core._validate_publication_times(
        definition,
        release,
        recorded_at=recorded_at,
        require_live=True,
    )
    assert all(
        path.stat(follow_symlinks=False).st_ctime + 1e-6 >= target.timestamp()
        for path in paths
    )
    assert core._identity(definition, directory=False) == definition_identity
    core._assert_tree_identities(release, release_identities)
    assert {path: path.read_bytes() for path in before} == before
    assert stat.S_IMODE(definition.stat().st_mode) == 0o444
    assert stat.S_IMODE(release.stat().st_mode) == 0o555
    assert stat.S_IMODE(nested.stat().st_mode) == 0o555
    assert stat.S_IMODE(member.stat().st_mode) == 0o444
    core._thaw_private_stage(definition, release)


def test_final_validation_failure_after_both_promotions_rolls_back_exactly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, releases, definition, release, lock = _publisher_roots(
        tmp_path, monkeypatch
    )
    _install_fast_publication_gates(monkeypatch)
    monkeypatch.setattr(
        core,
        "validate_open_seed_v97",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            core.OpenSeedV97Error("injected final validation failure")
        ),
    )
    _wall, recorded_at = _future()
    with pytest.raises(core.OpenSeedV97Error, match="injected final validation"):
        core.build_open_seed_v97(recorded_at=recorded_at, publication_authorized=True)
    _assert_no_publisher_residue(sources, releases, definition, release, lock)


@pytest.mark.parametrize("substituted", ["release", "definition"])
def test_substituted_published_inode_is_retained_during_final_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    substituted: str,
) -> None:
    sources, releases, definition, release, lock = _publisher_roots(
        tmp_path, monkeypatch
    )
    _install_fast_publication_gates(monkeypatch)
    displaced = (
        releases / ".displaced-original-release"
        if substituted == "release"
        else sources / ".displaced-original-definition"
    )
    foreign_payload = b"foreign inode retained\n"

    def substitute_then_fail(*_args: object, **_kwargs: object) -> dict[str, object]:
        target = release if substituted == "release" else definition
        target.rename(displaced)
        if substituted == "release":
            target.mkdir()
            foreign_member = target / "foreign.txt"
            foreign_member.write_bytes(foreign_payload)
        else:
            target.write_bytes(foreign_payload)
        raise core.OpenSeedV97Error(f"injected substituted {substituted}")

    monkeypatch.setattr(core, "validate_open_seed_v97", substitute_then_fail)
    _wall, recorded_at = _future()
    with pytest.raises(
        core.OpenSeedV97Error, match=f"injected substituted {substituted}"
    ) as error:
        core.build_open_seed_v97(recorded_at=recorded_at, publication_authorized=True)
    notes = getattr(error.value, "__notes__", [])
    assert any(
        f"substituted v97 {substituted}" in note
        or f"substituted published v97 {substituted}" in note
        for note in notes
    )
    assert displaced.exists()
    if substituted == "release":
        assert release.is_dir()
        assert (release / "foreign.txt").read_bytes() == foreign_payload
        assert not definition.exists()
        assert not list(sources.glob(f".{definition.name}.*.stage"))
    else:
        assert definition.is_file()
        assert definition.read_bytes() == foreign_payload
        assert not release.exists()
        assert not list(releases.glob(f".{release.name}.*"))
    assert not lock.exists()
    _remove_test_tree(displaced)
    _remove_test_tree(release if substituted == "release" else definition)


def test_late_collision_and_second_promotion_failure_roll_back_owned_stages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, releases, definition, release, lock = _publisher_roots(
        tmp_path, monkeypatch
    )
    _install_fast_publication_gates(monkeypatch)

    def collide(_target: datetime) -> None:
        definition.write_text("late collision")

    monkeypatch.setattr(core, "_wait_until", collide)
    _wall, recorded_at = _future()
    with pytest.raises(core.OpenSeedV97Error, match="late.*definition collision"):
        core.build_open_seed_v97(recorded_at=recorded_at, publication_authorized=True)
    assert definition.read_text() == "late collision"
    assert not release.exists()
    assert not lock.exists()
    definition.unlink()

    monkeypatch.setattr(core, "_wait_until", lambda _target: None)
    original = core._promote_noreplace

    def fail_second(
        stage: Path, destination: Path, *, directory: bool
    ) -> tuple[int, int]:
        if Path(destination) == definition:
            raise core.OpenSeedV97Error("definition promotion failure")
        return original(stage, destination, directory=directory)

    monkeypatch.setattr(core, "_promote_noreplace", fail_second)
    with pytest.raises(core.OpenSeedV97Error, match="definition promotion"):
        core.build_open_seed_v97(recorded_at=recorded_at, publication_authorized=True)
    _assert_no_publisher_residue(sources, releases, definition, release, lock)
