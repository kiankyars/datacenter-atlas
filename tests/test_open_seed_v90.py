from __future__ import annotations

import hashlib
import json

try:
    from datacenter_atlas.datacenter_atlas import open_seed_v90 as core
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import open_seed_v90 as core


def _pin(path) -> tuple[int, str]:
    raw = path.read_bytes()
    return len(raw), hashlib.sha256(raw).hexdigest()


def test_frozen_v90_exact_pins_and_offline_replays() -> None:
    assert _pin(core.DEFINITION) == (
        107_554,
        "3e224d0560e7f82fc31f7bdf6eb6b723ce50ad8423e2296de8c509b75c0fbdda",
    )
    assert _pin(core.RELEASE / "manifest.json") == (
        15_902,
        "40be71c613c74e4e843c5c60ad85ce172c206f72350df5a0996b7e971ca54b66",
    )
    assert _pin(core.RELEASE / "entities.csv") == (
        1_014_802,
        "732b1e8414532bf5ff9498b694678c9f4e6cacb83a2df4cadb7d135141d49aa8",
    )
    assert core.v69.tree_digest(core.RELEASE) == (
        "18cda7d054789dde956a393959cde79349f835927b1e757da364e15d974b78f3"
    )
    manifest = core.validate_open_seed_v90()
    assert manifest["recorded_at"] == "2026-07-22T01:16:53Z"


def test_v90_summary_and_v89_immutability_are_exact() -> None:
    summary = json.loads((core.RELEASE / "summary.json").read_text())
    assert {
        "entities_total": summary["entities_total"],
        "campuses_total": summary["campuses_total"],
        "projects_total": summary["projects_total"],
        "evidence_total": summary["evidence_total"],
        "lifecycle_observations_current": summary["lifecycle_observations_current"],
        "capacity_estimates_current": summary["capacity_estimates_current"],
        "construction_pipeline_records": summary["construction_pipeline_records"],
        "construction_source_signals": summary["construction_source_signals"],
        "entities_with_coordinates": summary["entities_with_coordinates"],
        "campuses_with_coordinates": summary["campuses_with_coordinates"],
    } == {
        "entities_total": 973,
        "campuses_total": 506,
        "projects_total": 467,
        "evidence_total": 793,
        "lifecycle_observations_current": 542,
        "capacity_estimates_current": 557,
        "construction_pipeline_records": 493,
        "construction_source_signals": 392,
        "entities_with_coordinates": 213,
        "campuses_with_coordinates": 141,
    }
    assert _pin(core.BASE_DEFINITION) == core.BASE_DEFINITION_PIN
    assert _pin(core.BASE_RELEASE / "manifest.json") == core.BASE_MANIFEST_PIN
    assert _pin(core.BASE_RELEASE / "entities.csv") == core.BASE_ENTITIES_PIN
    assert core.v69.tree_digest(core.BASE_RELEASE) == core.BASE_TREE_SHA256


def test_v90_has_no_stage_or_lock_residue() -> None:
    assert not core.PUBLICATION_LOCK.exists()
    assert not list(core.DEFINITION.parent.glob(f".{core.DEFINITION.name}.*.stage"))
    assert not list(core.RELEASE.parent.glob(f".{core.RELEASE.name}.*"))
