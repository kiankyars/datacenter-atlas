from __future__ import annotations

import hashlib
import json

try:
    from datacenter_atlas.datacenter_atlas import open_seed_v91 as core
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import open_seed_v91 as core


def _pin(path) -> tuple[int, str]:
    raw = path.read_bytes()
    return len(raw), hashlib.sha256(raw).hexdigest()


def test_frozen_v91_exact_pins_and_offline_replays() -> None:
    assert _pin(core.DEFINITION) == (
        108_188,
        "e1a1c657c88468233dc72e66012ec1f56afd69a599f129c5fcc64f20bdf3038a",
    )
    assert _pin(core.RELEASE / "manifest.json") == (
        15_954,
        "8be929e9f24b0bb1d11a318cfd67d8c4e538f2979db9468ecd359cb36afb45f9",
    )
    assert _pin(core.RELEASE / "entities.csv") == (
        1_018_118,
        "b1f07223ff1a61e64670aaf23bc9b3a7ee5834c2131e031a59401b404acebe75",
    )
    assert core.v69.tree_digest(core.RELEASE) == (
        "9c89ab93baf5a13965db764a376affe231186df6a5cbc2758fd9ad95a85a5a5e"
    )
    manifest = core.validate_open_seed_v91()
    assert manifest["recorded_at"] == "2026-07-22T01:33:29Z"


def test_v91_summary_and_v90_immutability_are_exact() -> None:
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
        "entities_total": 978,
        "campuses_total": 508,
        "projects_total": 470,
        "evidence_total": 798,
        "lifecycle_observations_current": 545,
        "capacity_estimates_current": 557,
        "construction_pipeline_records": 496,
        "construction_source_signals": 395,
        "entities_with_coordinates": 213,
        "campuses_with_coordinates": 141,
    }
    assert summary["entities_by_country"]["United States"] == 317
    assert summary["entities_by_status"]["under_construction"] == 381
    assert _pin(core.BASE_DEFINITION) == core.BASE_DEFINITION_PIN
    assert _pin(core.BASE_RELEASE / "manifest.json") == core.BASE_MANIFEST_PIN
    assert _pin(core.BASE_RELEASE / "entities.csv") == core.BASE_ENTITIES_PIN
    assert core.v69.tree_digest(core.BASE_RELEASE) == core.BASE_TREE_SHA256


def test_v91_exact_append_and_montgomery_byte_reuse() -> None:
    definition = json.loads(core.DEFINITION.read_text())
    base = json.loads(core.BASE_DEFINITION.read_text())
    assert definition["curated_inputs"][:477] == base["curated_inputs"]
    assert [row["path"] for row in definition["curated_inputs"][477:]] == list(
        core.ADDITION_ORDER
    )
    assert len(definition["curated_inputs"]) == 480
    montgomery = "epoch-ai:data-center:dec73855-d62c-5f35-bd1a-3b1f00b20bec"
    assert core._entity_csv_record(
        core.RELEASE / "entities.csv", montgomery
    ) == core._entity_csv_record(core.BASE_RELEASE / "entities.csv", montgomery)


def test_v91_has_no_stage_or_lock_residue() -> None:
    assert not core.PUBLICATION_LOCK.exists()
    assert not list(core.DEFINITION.parent.glob(f".{core.DEFINITION.name}.*.stage"))
    assert not list(core.RELEASE.parent.glob(f".{core.RELEASE.name}.*"))
