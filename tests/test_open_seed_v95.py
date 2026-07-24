from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import tempfile

import pytest

try:
    from datacenter_atlas.datacenter_atlas import open_seed_v95 as core
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import open_seed_v95 as core


def _future(minutes: int = 10) -> tuple[datetime, str]:
    target = datetime.now(UTC).replace(microsecond=0) + timedelta(minutes=minutes)
    return target, target.isoformat(timespec="seconds").replace("+00:00", "Z")


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_exact_v94_artifact_incident_and_source_lineage() -> None:
    guard = core._guard_state()
    core._validate_guard(guard)
    assert guard["base_definition"] == core.BASE_DEFINITION_PIN
    assert guard["base_manifest"] == core.BASE_MANIFEST_PIN
    assert guard["base_tree"] == core.BASE_TREE_SHA256
    assert guard["artifact_manifests"] == {
        spec.label: spec.manifest_pin for spec in core.ARTIFACT_SPECS
    }
    assert guard["artifact_trees"] == {
        spec.label: spec.physical_tree for spec in core.ARTIFACT_SPECS
    }
    assert guard["rejected_incident"] == core.REJECTED_INCIDENT_PIN
    assert guard["selected_sources"] == core.ADDITION_PINS


def test_nine_input_selection_replaces_northc_v1_and_adds_centra_last() -> None:
    base = json.loads(core.BASE_DEFINITION.read_text())
    wall, recorded_at = _future()
    selected, paths = core.selected_inputs(
        base, recorded_at=recorded_at, validation_wall_clock=wall
    )
    assert len(selected) == len(paths) == 507
    assert selected[: core.BASE_INPUT_COUNT] == base["curated_inputs"]
    assert [row["path"] for row in selected[core.BASE_INPUT_COUNT :]] == list(
        core.ADDITION_ORDER
    )
    assert core.NORTHC_SUCCESSOR in core.ADDITION_ORDER
    assert core.REJECTED_COORDINATE_V1_SUCCESSOR not in core.ADDITION_ORDER
    assert not any(
        path.endswith("northc-aalsmeer-phase-2-expansion.json")
        for path in core.ADDITION_ORDER
    )
    assert core.ADDITION_ORDER[-1].endswith(
        "centra-rno2-reno-shell-current-build.json"
    )


def test_private_database_and_public_release_contract() -> None:
    base = json.loads(core.BASE_DEFINITION.read_text())
    wall, recorded_at = _future()
    _selected, paths = core.selected_inputs(
        base, recorded_at=recorded_at, validation_wall_clock=wall
    )
    with tempfile.TemporaryDirectory(
        prefix="open-seed-v95-test-", dir="/private/tmp"
    ) as temporary:
        root = Path(temporary)
        connection = core._build_database(
            base, paths, root / "atlas.sqlite", recorded_at=recorded_at
        )
        try:
            assert {
                table: connection.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()[0]
                for table in core.EXPECTED_DATABASE_COUNTS
            } == core.EXPECTED_DATABASE_COUNTS
            release = root / "release"
            core._write_release(connection, release, recorded_at=recorded_at)
        finally:
            connection.close()
        core._validate_release_facts(release, recorded_at=recorded_at)
        manifest = json.loads((release / "manifest.json").read_text())
        assert manifest["internal_database_delta"] == core.INTERNAL_DELTA
        assert manifest["public_release_delta"] == core.PUBLIC_DELTA
        assert manifest["base_rows_frozen"] is True
        assert manifest["stale_status_suppression"] == core.STALE_POLICY
        assert manifest["coordinate_boundary"] == core.COORDINATE_BOUNDARY


def test_stale_status_suppression_is_addition_scoped_and_non_rehydratable() -> None:
    base = json.loads(core.BASE_DEFINITION.read_text())
    wall, recorded_at = _future()
    _selected, paths = core.selected_inputs(
        base, recorded_at=recorded_at, validation_wall_clock=wall
    )
    with tempfile.TemporaryDirectory(
        prefix="open-seed-v95-stale-", dir="/private/tmp"
    ) as temporary:
        root = Path(temporary)
        connection = core._build_database(
            base, paths, root / "atlas.sqlite", recorded_at=recorded_at
        )
        try:
            release = root / "release"
            core._write_release(connection, release, recorded_at=recorded_at)
        finally:
            connection.close()
        entities = {row["stable_key"]: row for row in _rows(release / "entities.csv")}
        for key in core.STALE_SUPPRESSED_PROJECT_KEYS:
            assert all(not entities[key][field] for field in core.STATUS_FIELDS)
        pipeline = {
            row["stable_key"] for row in _rows(release / "construction_pipeline.csv")
        }
        assert not pipeline & core.STALE_SUPPRESSED_PROJECT_KEYS
        freshness = {
            row["stable_key"]: row
            for row in _rows(release / "lifecycle_freshness.csv")
        }
        for key in core.STALE_SUPPRESSED_PROJECT_KEYS:
            assert freshness[key]["freshness_class"] == "stale_over_365_days"
            assert freshness[key]["current_status_classification"] == "unknown"
            assert freshness[key]["current_construction_claim"] == "false"
        signals = {
            row["representative_stable_key"]
            for row in _rows(release / "construction_source_signals.csv")
        }
        assert core.STALE_SUPPRESSED_PROJECT_KEYS <= signals
        assert core.STALE_POLICY["successor_rehydration_forbidden"] is True

        for filename, key in (
            ("entities.csv", "stable_key"),
            ("evidence.csv", "evidence_id"),
            ("lifecycle_freshness.csv", "stable_key"),
            ("construction_pipeline.csv", "stable_key"),
            ("construction_source_signals.csv", "source_observation_evidence_id"),
        ):
            before = {row[key]: row for row in _rows(core.BASE_RELEASE / filename)}
            after = {row[key]: row for row in _rows(release / filename)}
            assert all(after[row_key] == row for row_key, row in before.items())


def test_northc_address_point_and_typed_claim_boundaries() -> None:
    documents = core._validate_selected_documents()
    northc = documents[core.NORTHC_SUCCESSOR]
    for entity in ("campus", "project"):
        assert northc[entity]["coordinates"] == {
            "latitude": 52.25979593,
            "longitude": 4.77335841,
        }
    pdok = next(
        row
        for row in northc["evidence"]
        if row["key"] == core.coordinate.PDOK_EVIDENCE_KEY
    )
    assert pdok["metadata"]["horizontal_uncertainty_m"] == 50
    assert core.CAPACITY_CONTRACT == {
        (
            core.coordinate.NORTHC_PROJECT_KEY,
            "critical_it_mw",
            "planned",
            "MW",
            2.4,
            "2026-04-01",
            "reported",
        ),
        (
            "curated:iren-childress-ai-data-center-campus:horizons-1-4-current-build",
            "critical_it_mw",
            "contracted",
            "MW",
            200.0,
            "2025-11-02",
            "reported",
        ),
        (
            core.global_gap.BTM_PROJECT,
            "critical_it_mw",
            "planned",
            "MW",
            18.0,
            "2025-10-30",
            "reported",
        ),
    }
    assert core.MODEL_CONTRACT == {
        (core.global_gap.CIRION_CAMPUS, "colocation"),
        ("curated:centra-rno2-reno-data-center:current-build", "colocation"),
    }


def test_prepublication_replays_and_stops_before_barrier() -> None:
    if core.DEFINITION.exists() or core.RELEASE.exists():
        pytest.skip("v95 final paths are already published")
    result = core.prepare_open_seed_v95()
    assert result["status"] == "prepublication-validated"
    assert result["publication_authorized"] is False
    assert result["barrier"] == "stopped-before-no-replace-promotion"
    assert result["final_definition_absent"] is True
    assert result["final_release_absent"] is True
    assert not core.DEFINITION.exists()
    assert not core.RELEASE.exists()
    assert not core.PUBLICATION_LOCK.exists()


def test_publication_authorization_fails_closed() -> None:
    before = (
        core._pin(core.DEFINITION) if core.DEFINITION.exists() else None,
        core.v69.tree_digest(core.RELEASE) if core.RELEASE.exists() else None,
    )
    with pytest.raises(core.OpenSeedV95Error, match="publication.*requires"):
        core.build_open_seed_v95()
    after = (
        core._pin(core.DEFINITION) if core.DEFINITION.exists() else None,
        core.v69.tree_digest(core.RELEASE) if core.RELEASE.exists() else None,
    )
    assert after == before
    assert not core.PUBLICATION_LOCK.exists()


def test_live_publication_validates_and_is_existing_identical() -> None:
    if not core.DEFINITION.exists() or not core.RELEASE.exists():
        pytest.skip("v95 is not published yet")
    manifest = core.validate_open_seed_v95()
    result = core.build_open_seed_v95(publication_authorized=True)
    assert result["status"] == "existing-identical"
    target = core.v70.parse_utc(manifest["recorded_at"], label="recorded_at")
    paths = [
        core.DEFINITION,
        core.RELEASE,
        *core._release_descendants(core.RELEASE),
    ]
    assert all(
        max(path.stat().st_birthtime, path.stat().st_mtime)
        <= target.timestamp() + 1e-6
        for path in paths
    )
    assert all(
        path.stat().st_ctime + 1e-6 >= target.timestamp() for path in paths
    )
    assert not core.PUBLICATION_LOCK.exists()
    assert not list(core.DEFINITION.parent.glob(f".{core.DEFINITION.name}.*.stage"))
    assert not list(core.RELEASE.parent.glob(f".{core.RELEASE.name}.*"))


def test_atomic_publication_and_existing_identical_on_temp_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    target = datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=15)
    recorded_at = target.isoformat(timespec="seconds").replace("+00:00", "Z")
    try:
        first = core.build_open_seed_v95(
            recorded_at=recorded_at, publication_authorized=True
        )
        assert first["status"] == "published"
        second = core.build_open_seed_v95(publication_authorized=True)
        assert second["status"] == "existing-identical"
        manifest = core.validate_open_seed_v95(definition, release)
        assert manifest["recorded_at"] == recorded_at
        paths = [definition, release, *core._release_descendants(release)]
        assert max(
            max(path.stat().st_birthtime, path.stat().st_mtime)
            - target.timestamp()
            for path in paths
        ) <= 1e-6
        assert min(
            path.stat().st_ctime - target.timestamp() for path in paths
        ) >= -1e-6
        assert not lock.exists()
        assert not list(sources.glob(f".{definition.name}.*.stage"))
        assert not list(releases.glob(f".{release.name}.*"))
    finally:
        core._thaw_private_stage(definition, release)


def test_definition_collision_rolls_back_temp_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
            raise FileExistsError("injected v95 definition collision")
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
        core.build_open_seed_v95(
            recorded_at=recorded_at, publication_authorized=True
        )
    assert not definition.exists()
    assert not release.exists()
    assert not lock.exists()
    assert not list(sources.iterdir())
    assert not list(releases.iterdir())
