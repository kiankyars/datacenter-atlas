from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

import pytest

try:
    from datacenter_atlas.datacenter_atlas import open_seed_v94 as core
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import open_seed_v94 as core


def _pin(path: Path) -> tuple[int, str]:
    raw = path.read_bytes()
    return len(raw), hashlib.sha256(raw).hexdigest()


def _future(minutes: int = 10) -> tuple[datetime, str]:
    target = datetime.now(UTC).replace(microsecond=0) + timedelta(minutes=minutes)
    return target, target.isoformat(timespec="seconds").replace("+00:00", "Z")


def test_v93_and_four_artifact_incident_lineage_are_exact() -> None:
    guard = core._guard_state()
    core._validate_guard(guard)
    assert guard["base_definition"] == core.BASE_DEFINITION_PIN
    assert guard["base_manifest"] == core.BASE_MANIFEST_PIN
    assert guard["base_entities"] == core.BASE_ENTITIES_PIN
    assert guard["base_source_inputs"] == core.BASE_SOURCE_INPUTS_PIN
    assert guard["base_tree"] == core.BASE_TREE_SHA256
    assert guard["official_manifests"] == {
        label: spec["manifest_pin"] for label, spec in core.OFFICIAL_SPECS.items()
    }
    assert guard["official_trees"] == {
        label: spec["physical_tree"] for label, spec in core.OFFICIAL_SPECS.items()
    }
    assert guard["additions"] == core.ADDITION_PINS
    for spec in core.OFFICIAL_SPECS.values():
        artifact = core.ROOT / "source_artifacts" / spec["module"].ARTIFACT_ID
        assert artifact.stat().st_ctime_ns == spec["root_ctime_ns"]
        assert {
            path.name: (*_pin(path), path.stat().st_ctime_ns)
            for path in artifact.iterdir()
        } == spec["member_pins"]
    rejected = core.ROOT / "source_artifacts" / core.REJECTED_V1_ID
    assert rejected.stat().st_ctime_ns == core.REJECTED_V1_ROOT_CTIME_NS
    assert {
        path.name: (*_pin(path), path.stat().st_ctime_ns)
        for path in rejected.iterdir()
    } == core.REJECTED_V1_MEMBER_PINS
    assert dict(core.merlin_v2.V1_SOURCE_PINS) == core.REJECTED_V1_SOURCE_PINS


def test_exact_ten_input_selection_and_source_semantics() -> None:
    base = json.loads(core.BASE_DEFINITION.read_text())
    wall, recorded_at = _future()
    selected, paths = core.selected_inputs(
        base, recorded_at=recorded_at, validation_wall_clock=wall
    )
    assert len(selected) == len(paths) == 498
    assert selected[:488] == base["curated_inputs"]
    assert [row["path"] for row in selected[488:]] == list(core.ADDITION_ORDER)
    assert [row["sha256"] for row in selected[488:]] == [
        core.ADDITION_PINS[path][1] for path in core.ADDITION_ORDER
    ]
    documents = core._validate_official_artifact()
    assert len(documents) == 10
    assert {
        row["key"] for document in documents.values() for row in document["evidence"]
    } == core.ADDED_EVIDENCE_KEYS
    assert {
        (
            document[row["entity"]]["stable_key"],
            row["value"],
            row["as_of_date"],
            row["method"],
        )
        for document in documents.values()
        for row in document["lifecycle"]
    } == core.LIFECYCLE_CONTRACT
    assert {
        (
            document[row["entity"]]["stable_key"], row["metric"], row["stage"],
            row["unit"], float(row["base"]), row["as_of_date"], row["method"],
        )
        for document in documents.values()
        for row in document["capacities"]
    } == core.CAPACITY_CONTRACT
    assert {
        f"sources/{path.name}": path.stat().st_ctime_ns for path in paths[-10:]
    } == core.SOURCE_CTIME_NS


def test_private_database_and_public_projection_are_exact() -> None:
    base = json.loads(core.BASE_DEFINITION.read_text())
    wall, recorded_at = _future()
    _selected, paths = core.selected_inputs(
        base, recorded_at=recorded_at, validation_wall_clock=wall
    )
    with tempfile.TemporaryDirectory(
        prefix="open-seed-v94-test-", dir="/private/tmp"
    ) as temporary:
        root = Path(temporary)
        connection = core._build_database(
            base, paths, root / "atlas.sqlite", recorded_at=recorded_at
        )
        try:
            assert {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "entities",
                    "entity_snapshots",
                    "evidence",
                    "lifecycle_observations",
                    "capacity_estimates",
                )
            } == {
                "entities": 1011,
                "entity_snapshots": 1036,
                "evidence": 845,
                "lifecycle_observations": 585,
                "capacity_estimates": 565,
            }
            assert connection.execute(
                "SELECT COUNT(*) FROM operating_model_observations"
            ).fetchone()[0] == 74
            assert connection.execute(
                "SELECT COUNT(*) FROM workload_observations"
            ).fetchone()[0] == 136
            release = root / "release"
            core._write_release(connection, release, recorded_at=recorded_at)
        finally:
            connection.close()
        core._validate_release_facts(release, recorded_at=recorded_at)
        manifest = json.loads((release / "manifest.json").read_text())
        assert {
            key: manifest[key]
            for key in (
                "entities",
                "entities_by_kind",
                "evidence_records",
                "lifecycle_freshness_records",
                "capacity_estimates",
                "construction_pipeline_records",
                "construction_source_signals",
            )
        } == {
            "entities": 1011,
            "entities_by_kind": {"campus": 524, "project": 487},
            "evidence_records": 665,
            "lifecycle_freshness_records": 562,
            "capacity_estimates": 564,
            "construction_pipeline_records": 513,
            "construction_source_signals": 411,
        }
        summary = json.loads((release / "summary.json").read_text())
        assert summary["append_projection"]["internal_database_delta"] == {
            "entities": 17,
            "entity_snapshots": 19,
            "evidence": 20,
            "lifecycle_observations": 11,
            "capacity_estimates": 6,
            "operating_model_observations": 1,
            "workload_observations": 1,
        }
        assert summary["append_projection"]["public_release_delta"] == {
            "entities": 17,
            "evidence": 14,
            "lifecycle_freshness": 9,
            "capacity_estimates": 6,
            "construction_pipeline": 9,
            "construction_source_signals": 8,
        }


def test_partial_collision_fails_closed(tmp_path: Path, monkeypatch) -> None:
    definition = tmp_path / core.DEFINITION.name
    release = tmp_path / core.RELEASE.name
    lock = tmp_path / core.PUBLICATION_LOCK.name
    definition.write_text("collision\n", encoding="utf-8")
    monkeypatch.setattr(core, "DEFINITION", definition)
    monkeypatch.setattr(core, "RELEASE", release)
    monkeypatch.setattr(core, "PUBLICATION_LOCK", lock)
    with pytest.raises(core.OpenSeedV94Error, match="partial"):
        core.build_open_seed_v94()


def test_definition_collision_rolls_back_release(tmp_path: Path, monkeypatch) -> None:
    sources = tmp_path / "sources"
    releases = tmp_path / "releases"
    sources.mkdir()
    releases.mkdir()
    definition = sources / core.DEFINITION.name
    release = releases / core.RELEASE.name
    lock = tmp_path / core.PUBLICATION_LOCK.name
    original = core.v69.promote_noreplace

    def collide(source: Path, destination: Path) -> None:
        if Path(destination) == definition:
            raise FileExistsError("injected v94 definition collision")
        original(source, destination)

    _target, recorded_at = _future()
    monkeypatch.setattr(core, "DEFINITION", definition)
    monkeypatch.setattr(core, "RELEASE", release)
    monkeypatch.setattr(core, "PUBLICATION_LOCK", lock)
    monkeypatch.setattr(core, "_wait_until", lambda _target: None)
    monkeypatch.setattr(core, "_refresh_publication_ctimes", lambda *_args: None)
    monkeypatch.setattr(
        core, "_validate_publication_times", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(core.v69, "promote_noreplace", collide)
    with pytest.raises(FileExistsError, match="injected"):
        core.build_open_seed_v94(recorded_at=recorded_at)
    assert not definition.exists()
    assert not release.exists()
    assert not lock.exists()
    assert not list(sources.iterdir())
    assert not list(releases.iterdir())


def test_live_release_future_and_tamper_guards(tmp_path: Path) -> None:
    if not core.DEFINITION.exists():
        pytest.skip("v94 is not published yet")
    manifest = core.validate_open_seed_v94()
    before = core.v70.parse_utc(
        manifest["recorded_at"], label="recorded_at"
    ) - timedelta(microseconds=1)
    with pytest.raises(core.OpenSeedV94Error, match="validation wall clock"):
        core.validate_open_seed_v94(validation_wall_clock=before)

    definition = tmp_path / core.DEFINITION.name
    release = tmp_path / core.RELEASE.name
    shutil.copy2(core.DEFINITION, definition)
    shutil.copytree(core.RELEASE, release)
    release.chmod(0o755)
    target = release / "summary.json"
    target.chmod(0o644)
    target.write_bytes(target.read_bytes() + b" ")
    target.chmod(0o444)
    release.chmod(0o555)
    with pytest.raises(core.OpenSeedV94Error, match="release pin differs"):
        core.validate_open_seed_v94(
            definition,
            release,
            validation_wall_clock=datetime.now(UTC),
            require_live=False,
        )


def test_live_release_idempotence_and_ctimes() -> None:
    if not core.DEFINITION.exists():
        pytest.skip("v94 is not published yet")
    result = core.build_open_seed_v94()
    assert result["status"] == "existing-identical"
    manifest = core.validate_open_seed_v94()
    target = core.v70.parse_utc(manifest["recorded_at"], label="recorded_at")
    for path in (core.DEFINITION, core.RELEASE, *core.RELEASE.iterdir()):
        assert path.stat(follow_symlinks=False).st_ctime >= target.timestamp()


def test_v94_has_no_stage_or_lock_residue() -> None:
    assert not core.PUBLICATION_LOCK.exists()
    assert not list(core.DEFINITION.parent.glob(f".{core.DEFINITION.name}.*.stage"))
    assert not list(core.RELEASE.parent.glob(f".{core.RELEASE.name}.*"))
