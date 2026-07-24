from __future__ import annotations

import hashlib
import json

try:
    from datacenter_atlas.datacenter_atlas import open_seed_v89 as core
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import open_seed_v89 as core


def _pin(path) -> tuple[int, str]:
    raw = path.read_bytes()
    return len(raw), hashlib.sha256(raw).hexdigest()


def test_frozen_v89_exact_pins_and_offline_replays() -> None:
    assert _pin(core.DEFINITION) == (
        105_962,
        "1c9be663976b1b5e93f31868df73f76e66498f14ef9eff157baefb8144b8289b",
    )
    assert _pin(core.RELEASE / "manifest.json") == (
        15_707,
        "07f2f521f365b4427c08a7393f72977a68137aa87f9ea015ccf480cac455f9b2",
    )
    assert core.v69.tree_digest(core.RELEASE) == (
        "83b721b2066c3be6cbf3cf3bfb255abb8ed4427ad5ebd17da8dcc5214551fdad"
    )
    manifest = core.validate_open_seed_v89()
    assert manifest["recorded_at"] == "2026-07-22T00:57:44Z"


def test_v89_summary_and_v88_immutability_are_exact() -> None:
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
        "entities_total": 959,
        "campuses_total": 499,
        "projects_total": 460,
        "evidence_total": 784,
        "lifecycle_observations_current": 535,
        "capacity_estimates_current": 557,
        "construction_pipeline_records": 486,
        "construction_source_signals": 386,
        "entities_with_coordinates": 213,
        "campuses_with_coordinates": 141,
    }
    assert _pin(core.BASE_DEFINITION) == core.BASE_DEFINITION_PIN
    assert _pin(core.BASE_RELEASE / "manifest.json") == core.BASE_MANIFEST_PIN
    assert _pin(core.BASE_RELEASE / "entities.csv") == core.BASE_ENTITIES_PIN
    assert core.v69.tree_digest(core.BASE_RELEASE) == core.BASE_TREE_SHA256


def test_v89_has_no_stage_or_lock_residue() -> None:
    assert not core.PUBLICATION_LOCK.exists()
    assert not list(core.DEFINITION.parent.glob(f".{core.DEFINITION.name}.*.stage"))
    assert not list(core.RELEASE.parent.glob(f".{core.RELEASE.name}.*"))
