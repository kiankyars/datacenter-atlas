from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import shutil
import tempfile

import pytest

try:
    from datacenter_atlas.datacenter_atlas import open_seed_v96 as core
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import open_seed_v96 as core


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


def _install_fast_publication_gates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def validate(
        definition_path: Path,
        release_path: Path,
        **_kwargs: object,
    ) -> dict[str, object]:
        definition = json.loads(definition_path.read_text())
        manifest = core._validate_release_facts(
            release_path,
            recorded_at=definition["build"]["recorded_at"],
        )
        return {
            **manifest,
            "two_replay_manifest_sha256": core._sha256(
                (release_path / "manifest.json").read_bytes()
            ),
        }

    monkeypatch.setattr(core, "validate_staged_open_seed_v96", validate)
    monkeypatch.setattr(core, "validate_open_seed_v96", validate)
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


def test_exact_v95_base_and_all_four_accepted_artifacts_are_ready() -> None:
    guard = core._guard_state()
    core._validate_guard(guard)
    report = core.readiness_report()
    assert report["status"] == "ready"
    assert report["barrier"] is None
    assert report["base_definition_sha256"] == core.BASE_DEFINITION_PIN[1]
    assert report["base_tree_sha256"] == core.BASE_TREE_SHA256
    assert report["accepted_artifacts_validated"] == [
        "nordic",
        "gdh",
        "regional",
        "nxdata",
    ]
    assert report["nxdata_live_artifact_pin"] == {
        "recorded_at": core.NXDATA_LIVE_RECORDED_AT,
        "manifest_bytes": core.NXDATA_LIVE_MANIFEST_PIN[0],
        "manifest_sha256": core.NXDATA_LIVE_MANIFEST_PIN[1],
        "tree_sha256": core.NXDATA_LIVE_TREE_SHA256,
    }
    assert report["final_definition_absent"] is True
    assert report["final_release_absent"] is True
    assert report["publication_lock_absent"] is True


def test_selection_replaces_fin04_in_place_and_preserves_506_other_rows() -> None:
    base, selected, paths = _planned()
    rows = base["curated_inputs"]
    assert isinstance(rows, list)
    assert len(selected) == len(paths) == 516
    assert selected[:174] == rows[:174]
    assert selected[175 : core.BASE_INPUT_COUNT] == rows[175:]
    assert selected[174] == {
        "path": core.FIN04_SUCCESSOR,
        "sha256": core.NON_NXDATA_PINS[core.FIN04_SUCCESSOR][1],
    }
    assert [row["path"] for row in selected[core.BASE_INPUT_COUNT :]] == list(
        core.APPEND_ORDER
    )
    assert core.FIN04_PREDECESSOR not in {row["path"] for row in selected}
    assert sum(row["path"] == core.FIN04_SUCCESSOR for row in selected) == 1


def test_source_claims_pin_collisions_metrics_and_stale_boundary() -> None:
    accepted = core._validate_non_nxdata_inputs()
    documents = {**accepted, core.NXDATA_SOURCE: core._validate_nxdata_final()}
    contract = core._claim_contract(documents)
    assert contract["capacities"] == core.EXPECTED_CAPACITIES
    assert contract["models"] == core.EXPECTED_MODELS
    assert contract["newly_stale"] == {core.ORAN_PROJECT_KEY}
    assert contract["stable_keys"] - core.FIN04_KEYS == core.ADDED_ENTITY_KEYS
    assert len(contract["evidence_keys"]) == 19
    assert core.EXPECTED_STALE_PROJECT_KEYS == (
        core.v95.STALE_SUPPRESSED_PROJECT_KEYS | {core.ORAN_PROJECT_KEY}
    )
    nxdata = documents[core.NXDATA_SOURCE]
    assert all(
        row["evidence_key"] == "nxdata3-technical-brochure-captured-2026-07-22"
        and row["low"] == row["base"] == row["high"]
        and row["as_of_date"] == "2025-07-11"
        and row["method"] == "reported"
        for row in nxdata["capacities"]
    )
    assert not any(document["workloads"] for document in documents.values())
    assert all(
        document[entity]["coordinates"] is None and document[entity]["geometry"] is None
        for document in documents.values()
        for entity in ("campus", "project")
    )


def test_real_database_and_renderer_enforce_exact_v96_projection() -> None:
    base, _selected, paths = _planned()
    with tempfile.TemporaryDirectory(
        prefix="open-seed-v96-render-test-", dir="/private/tmp"
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
            core._write_release(
                connection,
                release,
                recorded_at="2099-01-01T00:00:00Z",
            )
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
            "entities": 1_047,
            "evidence_records": 690,
            "lifecycle_freshness_records": 580,
            "capacity_estimates": 570,
            "construction_pipeline_records": 528,
            "construction_source_signals": 429,
        }
        assert manifest["governed_base_row_replacements"] == (
            core.GOVERNED_REPLACEMENTS
        )
        assert "append_only_base_release" not in manifest

        entities = {row["stable_key"]: row for row in _rows(release / "entities.csv")}
        for key in core.EXPECTED_STALE_PROJECT_KEYS:
            assert all(not entities[key][field] for field in core.v95.STATUS_FIELDS)
        pipeline = {
            row["stable_key"] for row in _rows(release / "construction_pipeline.csv")
        }
        assert not pipeline & core.EXPECTED_STALE_PROJECT_KEYS
        signals = {
            row["representative_stable_key"]
            for row in _rows(release / "construction_source_signals.csv")
        }
        assert core.EXPECTED_STALE_PROJECT_KEYS <= signals
        assert (
            len(json.loads((release / "source_inputs.json").read_text())["sources"])
            == 617
        )


def test_unrelated_v95_public_rows_are_frozen() -> None:
    base, _selected, paths = _planned()
    with tempfile.TemporaryDirectory(
        prefix="open-seed-v96-freeze-test-", dir="/private/tmp"
    ) as temporary:
        root = Path(temporary)
        connection = core._build_database(
            base,
            paths,
            root / "atlas.sqlite",
            recorded_at="2099-01-01T00:00:00Z",
        )
        try:
            release = root / "release"
            core._write_release(
                connection,
                release,
                recorded_at="2099-01-01T00:00:00Z",
            )
        finally:
            connection.close()
        expectations = {
            "entities.csv": ("stable_key", core.FIN04_KEYS),
            "evidence.csv": ("evidence_id", frozenset()),
            "lifecycle_freshness.csv": (
                "stable_key",
                frozenset({core.FIN04_PROJECT_KEY}),
            ),
            "construction_pipeline.csv": (
                "stable_key",
                frozenset({core.FIN04_PROJECT_KEY}),
            ),
            "construction_source_signals.csv": (
                "source_observation_evidence_id",
                frozenset(),
            ),
        }
        for filename, (key, replacements) in expectations.items():
            before = {row[key]: row for row in _rows(core.BASE_RELEASE / filename)}
            after = {row[key]: row for row in _rows(release / filename)}
            for row_key in set(before) & set(after) - replacements:
                assert after[row_key] == before[row_key]
        for filename in ("resolution_candidates.csv", "resolution_candidates.json"):
            assert (release / filename).read_bytes() == (
                core.BASE_RELEASE / filename
            ).read_bytes()


def test_full_prepublication_runs_two_replays_and_leaves_no_final() -> None:
    result = core.prepare_open_seed_v96()
    assert result["status"] == "prepublication-validated"
    assert result["publication_authorized"] is False
    assert result["barrier"] == "stopped-before-final-no-replace-promotion"
    assert result["planned_input_count"] == 516
    assert result["manifest_sha256"] == result["two_replay_manifest_sha256"]
    assert result["private_no_replace_roundtrip_validated"] is True
    assert result["final_definition_absent"] is True
    assert result["final_release_absent"] is True
    assert result["publication_lock_absent"] is True
    assert not core.DEFINITION.exists()
    assert not core.RELEASE.exists()
    assert not core.PUBLICATION_LOCK.exists()


def test_unreviewed_nxdata_live_pin_blocks_before_staging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(core, "NXDATA_LIVE_MANIFEST_PIN", None)
    monkeypatch.setattr(core, "NXDATA_LIVE_TREE_SHA256", None)
    report = core.readiness_report()
    assert report["status"] == "blocked"
    assert report["barrier"] == "nxdata_live_pin_unreviewed"
    with pytest.raises(core.OpenSeedV96ReadinessError) as error:
        core.prepare_open_seed_v96()
    assert error.value.code == "nxdata_live_pin_unreviewed"
    assert not core.DEFINITION.exists()
    assert not core.RELEASE.exists()


def test_prospective_nxdata_artifact_pin_cannot_pass_live_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        core, "NXDATA_LIVE_MANIFEST_PIN", core.NXDATA_PROSPECTIVE_MANIFEST_PIN
    )
    monkeypatch.setattr(
        core, "NXDATA_LIVE_TREE_SHA256", core.NXDATA_PROSPECTIVE_TREE_SHA256
    )
    with pytest.raises(core.OpenSeedV96Error, match="live artifact pin differs"):
        core._validate_nxdata_final()


def test_exactly_two_replay_digest_gate_is_lowercase_hex() -> None:
    digest = "a" * 64
    assert core._two_replay_gate([digest, digest]) == digest
    for invalid in (
        [digest],
        [digest, "b" * 64],
        ["z" * 64, "z" * 64],
        ["A" * 64, "A" * 64],
        [digest, digest, digest],
    ):
        with pytest.raises(core.OpenSeedV96Error, match="replay"):
            core._two_replay_gate(invalid)


def test_wrong_replay_count_fails_before_any_stage() -> None:
    with pytest.raises(core.OpenSeedV96Error, match="exactly two"):
        core.prepare_open_seed_v96(replay_count=1)
    assert not core.DEFINITION.exists()
    assert not core.RELEASE.exists()
    assert not core.PUBLICATION_LOCK.exists()


def test_file_and_recursive_directory_no_replace_roundtrip(tmp_path: Path) -> None:
    file_stage = tmp_path / "definition.stage"
    file_stage.write_text("definition")
    file_destination = tmp_path / "definition.final"
    file_identity = core._promote_noreplace(
        file_stage, file_destination, directory=False
    )
    assert core._has_identity(file_destination, file_identity, directory=False)
    core._rollback_noreplace(
        file_destination, file_stage, file_identity, directory=False
    )
    assert core._has_identity(file_stage, file_identity, directory=False)

    release_stage = tmp_path / "release.stage"
    release_stage.mkdir()
    (release_stage / "member").write_text("release")
    release_identities = core._tree_identities(release_stage)
    release_destination = tmp_path / "release.final"
    release_identity = core._promote_noreplace(
        release_stage, release_destination, directory=True
    )
    core._assert_tree_identities(release_destination, release_identities)
    core._rollback_noreplace(
        release_destination, release_stage, release_identity, directory=True
    )
    core._assert_tree_identities(release_stage, release_identities)


def test_no_replace_collision_and_identity_mismatch_refuse_rollback(
    tmp_path: Path,
) -> None:
    stage = tmp_path / "stage"
    stage.write_text("stage")
    destination = tmp_path / "destination"
    destination.write_text("occupied")
    with pytest.raises(core.OpenSeedV96Error, match="collision|refusing overwrite"):
        core._promote_noreplace(stage, destination, directory=False)
    assert stage.read_text() == "stage"
    assert destination.read_text() == "occupied"

    destination.unlink()
    identity = core._promote_noreplace(stage, destination, directory=False)
    displaced = tmp_path / "displaced"
    destination.rename(displaced)
    destination.write_text("substitute")
    with pytest.raises(core.OpenSeedV96Error, match="identity-mismatched"):
        core._rollback_noreplace(destination, stage, identity, directory=False)


def test_recursive_identity_detects_descendant_substitution(tmp_path: Path) -> None:
    release = tmp_path / "release"
    release.mkdir()
    member = release / "member"
    member.write_text("accepted")
    identities = core._tree_identities(release)
    displaced = release / "displaced"
    member.rename(displaced)
    member.write_text("substitute")
    with pytest.raises(core.OpenSeedV96Error, match="recursive tree identity"):
        core._assert_tree_identities(release, identities)


def test_publication_requires_explicit_authorization() -> None:
    with pytest.raises(core.OpenSeedV96Error, match="requires explicit"):
        core.build_open_seed_v96()
    assert not core.DEFINITION.exists()
    assert not core.RELEASE.exists()
    assert not core.PUBLICATION_LOCK.exists()


def test_private_publication_is_release_first_frozen_and_existing_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, releases, definition, release, lock = _publisher_roots(
        tmp_path, monkeypatch
    )
    _install_fast_publication_gates(monkeypatch)
    original = core._promote_noreplace
    promotions: list[tuple[Path, Path]] = []

    def observe(stage: Path, destination: Path, *, directory: bool) -> tuple[int, int]:
        promotions.append((Path(stage), Path(destination)))
        assert Path(stage).parent == Path(destination).parent
        return original(stage, destination, directory=directory)

    monkeypatch.setattr(core, "_promote_noreplace", observe)
    _wall, recorded_at = _future()
    try:
        first = core.build_open_seed_v96(
            recorded_at=recorded_at, publication_authorized=True
        )
        second = core.build_open_seed_v96(publication_authorized=True)
        assert first["status"] == "published"
        assert second["status"] == "existing-identical"
        assert first["recorded_at"] == second["recorded_at"] == recorded_at
        assert first["manifest_sha256"] == second["manifest_sha256"]
        with pytest.raises(
            core.OpenSeedV96Error, match="existing.*recorded_at differs"
        ):
            core.build_open_seed_v96(
                recorded_at="2099-01-01T00:00:00Z",
                publication_authorized=True,
            )
        assert [destination for _stage, destination in promotions] == [
            release,
            definition,
        ]
        assert definition.stat().st_mode & 0o777 == 0o444
        assert release.stat().st_mode & 0o777 == 0o555
        assert all(path.stat().st_mode & 0o777 == 0o444 for path in release.iterdir())
        assert not lock.exists()
        assert not list(sources.glob(f".{definition.name}.*.stage"))
        assert not list(releases.glob(f".{release.name}.*"))
    finally:
        core._thaw_private_stage(definition, release)


def test_publisher_rejects_nonfuture_recorded_at_before_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, releases, definition, release, lock = _publisher_roots(
        tmp_path, monkeypatch
    )
    past = datetime.now(UTC).replace(microsecond=0) - timedelta(seconds=1)
    with pytest.raises(core.OpenSeedV96Error, match="future before staging"):
        core.build_open_seed_v96(
            recorded_at=past.isoformat(timespec="seconds").replace("+00:00", "Z"),
            publication_authorized=True,
        )
    _assert_no_publisher_residue(sources, releases, definition, release, lock)


@pytest.mark.parametrize("collision", ["definition", "release"])
def test_partial_final_collision_fails_before_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, collision: str
) -> None:
    sources, releases, definition, release, lock = _publisher_roots(
        tmp_path, monkeypatch
    )
    if collision == "definition":
        definition.write_text("collision")
    else:
        release.mkdir()
    _wall, recorded_at = _future()
    with pytest.raises(core.OpenSeedV96Error, match="partial"):
        core.build_open_seed_v96(recorded_at=recorded_at, publication_authorized=True)
    assert not lock.exists()
    assert not list(sources.glob(f".{definition.name}.*.stage"))
    assert not list(releases.glob(f".{release.name}.*"))


def test_existing_lock_and_lock_initialization_failure_leave_no_new_residue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, releases, definition, release, lock = _publisher_roots(
        tmp_path, monkeypatch
    )
    lock.write_text("other writer")
    _wall, recorded_at = _future()
    with pytest.raises(core.OpenSeedV96Error, match="active.*lock"):
        core.build_open_seed_v96(recorded_at=recorded_at, publication_authorized=True)
    assert lock.read_text() == "other writer"
    lock.unlink()

    monkeypatch.setattr(
        core.os,
        "write",
        lambda *_args: (_ for _ in ()).throw(OSError("injected lock write")),
    )
    with pytest.raises(OSError, match="injected lock write"):
        core.build_open_seed_v96(recorded_at=recorded_at, publication_authorized=True)
    _assert_no_publisher_residue(sources, releases, definition, release, lock)


def test_lock_fstat_initialization_failure_retries_identity_and_cleans_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sources, _releases, _definition, _release, lock = _publisher_roots(
        tmp_path, monkeypatch
    )
    original = core.os.fstat
    calls = 0

    def fail_once(descriptor: int) -> object:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("injected lock fstat failure")
        return original(descriptor)

    monkeypatch.setattr(core.os, "fstat", fail_once)
    with pytest.raises(OSError, match="injected lock fstat"):
        with core._publication_lock():
            pytest.fail("lock body must not run")
    assert calls == 2
    assert not lock.exists()


def test_early_build_failure_cleans_same_parent_stages_and_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, releases, definition, release, lock = _publisher_roots(
        tmp_path, monkeypatch
    )
    monkeypatch.setattr(
        core,
        "_build_database",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            core.OpenSeedV96Error("injected database failure")
        ),
    )
    _wall, recorded_at = _future()
    with pytest.raises(core.OpenSeedV96Error, match="injected database"):
        core.build_open_seed_v96(recorded_at=recorded_at, publication_authorized=True)
    _assert_no_publisher_residue(sources, releases, definition, release, lock)


def test_definition_identity_initialization_failure_closes_and_cleans_stages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, releases, definition, release, lock = _publisher_roots(
        tmp_path, monkeypatch
    )
    original = core._identity
    injected = False

    def fail_once(path: Path, *, directory: bool) -> tuple[int, int]:
        nonlocal injected
        if not directory and path.parent == sources and not injected:
            injected = True
            raise core.OpenSeedV96Error("injected definition identity failure")
        return original(path, directory=directory)

    monkeypatch.setattr(core, "_identity", fail_once)
    _wall, recorded_at = _future()
    with pytest.raises(core.OpenSeedV96Error, match="injected definition identity"):
        core.build_open_seed_v96(recorded_at=recorded_at, publication_authorized=True)
    assert injected is True
    _assert_no_publisher_residue(sources, releases, definition, release, lock)


def test_late_collision_cleans_owned_stages_without_removing_collision(
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
    with pytest.raises(core.OpenSeedV96Error, match="late.*definition collision"):
        core.build_open_seed_v96(recorded_at=recorded_at, publication_authorized=True)
    assert definition.read_text() == "late collision"
    assert not release.exists()
    assert not lock.exists()
    assert not list(sources.glob(f".{definition.name}.*.stage"))
    assert not list(releases.glob(f".{release.name}.*"))


def test_second_promotion_failure_rolls_release_back_and_cleans_everything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, releases, definition, release, lock = _publisher_roots(
        tmp_path, monkeypatch
    )
    _install_fast_publication_gates(monkeypatch)
    original = core._promote_noreplace

    def fail_second(
        stage: Path, destination: Path, *, directory: bool
    ) -> tuple[int, int]:
        if Path(destination) == definition:
            raise core.OpenSeedV96Error("injected definition promotion failure")
        return original(stage, destination, directory=directory)

    monkeypatch.setattr(core, "_promote_noreplace", fail_second)
    _wall, recorded_at = _future()
    with pytest.raises(core.OpenSeedV96Error, match="injected definition"):
        core.build_open_seed_v96(recorded_at=recorded_at, publication_authorized=True)
    _assert_no_publisher_residue(sources, releases, definition, release, lock)


def test_final_validation_failure_rolls_both_promotions_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, releases, definition, release, lock = _publisher_roots(
        tmp_path, monkeypatch
    )
    _install_fast_publication_gates(monkeypatch)
    monkeypatch.setattr(
        core,
        "validate_open_seed_v96",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            core.OpenSeedV96Error("injected final validation failure")
        ),
    )
    _wall, recorded_at = _future()
    with pytest.raises(core.OpenSeedV96Error, match="injected final validation"):
        core.build_open_seed_v96(recorded_at=recorded_at, publication_authorized=True)
    _assert_no_publisher_residue(sources, releases, definition, release, lock)


def test_identity_mismatch_refuses_release_rollback_but_cleans_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, releases, definition, release, lock = _publisher_roots(
        tmp_path, monkeypatch
    )
    _install_fast_publication_gates(monkeypatch)
    original = core._promote_noreplace
    displaced = releases / ".displaced-accepted-release"

    def substitute_before_second(
        stage: Path, destination: Path, *, directory: bool
    ) -> tuple[int, int]:
        if Path(destination) == definition:
            release.rename(displaced)
            release.mkdir()
            raise core.OpenSeedV96Error("injected second promotion failure")
        return original(stage, destination, directory=directory)

    monkeypatch.setattr(core, "_promote_noreplace", substitute_before_second)
    _wall, recorded_at = _future()
    with pytest.raises(core.OpenSeedV96Error, match="injected second") as error:
        core.build_open_seed_v96(recorded_at=recorded_at, publication_authorized=True)
    assert any("substituted v96 release" in note for note in error.value.__notes__)
    assert release.is_dir()
    assert displaced.is_dir()
    assert not definition.exists()
    assert not lock.exists()
    assert not list(sources.glob(f".{definition.name}.*.stage"))
    assert not list(releases.glob(f".{release.name}.*"))
    core._thaw_private_stage(tmp_path / "absent", displaced)
    shutil.rmtree(displaced)
    release.rmdir()


def test_wait_slices_and_recursive_publication_chronology(
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
    identities = core._tree_identities(release)
    definition_identity = core._identity(definition, directory=False)
    before = {path: path.read_bytes() for path in (definition, member)}
    target = datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=1)
    recorded_at = target.isoformat(timespec="seconds").replace("+00:00", "Z")
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
    assert core._identity(definition, directory=False) == definition_identity
    core._assert_tree_identities(release, identities)
    assert {path: path.read_bytes() for path in before} == before
    assert definition.stat().st_mode & 0o777 == 0o444
    assert release.stat().st_mode & 0o777 == 0o555
    assert nested.stat().st_mode & 0o777 == 0o555
    assert member.stat().st_mode & 0o777 == 0o444
    core._thaw_private_stage(definition, release)


def test_recorded_at_must_follow_all_accepted_artifacts() -> None:
    base = core._validate_base()
    wall, _future_timestamp = _future()
    with pytest.raises(core.OpenSeedV96Error, match="precedes an input"):
        core.selected_inputs(
            base,
            recorded_at="2026-07-22T04:50:00Z",
            validation_wall_clock=wall,
        )
