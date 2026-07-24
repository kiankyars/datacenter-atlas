from __future__ import annotations

from collections import Counter
import hashlib
import inspect
import json
from pathlib import Path
import stat

import pytest

try:
    from datacenter_atlas.datacenter_atlas import (
        satellite_unknown035_continuation_acceptance as acceptance,
    )
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import (  # type: ignore[no-redef]
        satellite_unknown035_continuation_acceptance as acceptance,
    )


MANIFEST_SHA256 = "1fd9851e7ab43bc7865c62c47abddb009c4fc69058ef8dd86db5b9da88b1e9b9"
DELTA_SHA256 = "ed9be3eedd4ceddd9028275e47931ee735784f17870874288d7fbbd727820fff"


@pytest.fixture(scope="module")
def accepted() -> tuple[dict[str, object], dict[str, object]]:
    manifest = acceptance.validate_unknown035_continuation_acceptance()
    delta = json.loads(
        (acceptance.OUTPUT / acceptance.DELTA_FILENAME).read_text(encoding="utf-8")
    )
    return manifest, delta


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _inventory_rows(raw: bytes) -> list[tuple[str, int, str]]:
    rows: list[tuple[str, int, str]] = []
    for line in raw.splitlines():
        path, size, digest = line.decode("utf-8").split("\0")
        rows.append((path, int(size), digest))
    return rows


def test_manifest_is_canonical_hash_bound_and_pins_current_inputs(
    accepted: tuple[dict[str, object], dict[str, object]],
) -> None:
    manifest, _delta = accepted
    raw = (acceptance.OUTPUT / acceptance.MANIFEST_FILENAME).read_bytes()
    assert raw == acceptance._canonical_json(manifest)
    assert len(raw) == 9_766
    assert _sha256(raw) == MANIFEST_SHA256
    assert (acceptance.OUTPUT / acceptance.SIDECAR_FILENAME).read_text(
        encoding="ascii"
    ) == (f"{MANIFEST_SHA256}  {acceptance.MANIFEST_FILENAME}\n")
    assert manifest["artifact_id"] == acceptance.ARTIFACT_ID
    assert manifest["format"] == (
        "datacenter-atlas-satellite-catalog-continuation-acceptance-v1"
    )
    assert manifest["schema_version"] == 1

    pins = (
        manifest["source_continuation"]["acceptance_manifest"],
        manifest["source_continuation"]["acceptance_sidecar"],
        manifest["source_continuation"]["batch_manifest"],
        manifest["queue_bundle"]["manifest"],
        manifest["queue_bundle"]["queue"],
        manifest["output"]["batch_manifest"],
        *manifest["execution"]["runner"].values(),
        *manifest["builder"]["files"].values(),
    )
    for expected in pins:
        path = acceptance.ROOT / expected["path"]
        assert not path.is_symlink()
        assert acceptance._path_record(path) == expected


def test_complete_canonical_inventories_are_embedded_and_exact(
    accepted: tuple[dict[str, object], dict[str, object]],
) -> None:
    manifest, _delta = accepted
    source_raw = (acceptance.OUTPUT / acceptance.SOURCE_INVENTORY_FILENAME).read_bytes()
    destination_raw = (
        acceptance.OUTPUT / acceptance.DESTINATION_INVENTORY_FILENAME
    ).read_bytes()
    source_rows = _inventory_rows(source_raw)
    destination_rows = _inventory_rows(destination_raw)

    assert len(source_rows) == acceptance.SOURCE_INVENTORY["files"] == 13_437
    assert len(destination_rows) == acceptance.DESTINATION_INVENTORY["files"] == 13_512
    assert sum(row[1] for row in source_rows) == 3_108_654_345
    assert sum(row[1] for row in destination_rows) == 3_120_154_596
    assert _sha256(source_raw) == acceptance.SOURCE_INVENTORY["sha256"]
    assert _sha256(destination_raw) == acceptance.DESTINATION_INVENTORY["sha256"]
    assert manifest["source_continuation"]["inventory"] == (acceptance.SOURCE_INVENTORY)
    assert manifest["output"]["inventory"] == acceptance.DESTINATION_INVENTORY
    assert [row[0] for row in source_rows] == sorted(row[0] for row in source_rows)
    assert [row[0] for row in destination_rows] == sorted(
        row[0] for row in destination_rows
    )


def test_clone_delta_is_only_new_catalog_triples_and_updated_manifest(
    accepted: tuple[dict[str, object], dict[str, object]],
) -> None:
    manifest, delta = accepted
    delta_raw = (acceptance.OUTPUT / acceptance.DELTA_FILENAME).read_bytes()
    assert delta_raw == acceptance._canonical_json(delta)
    assert _sha256(delta_raw) == DELTA_SHA256
    assert delta["summary"] == acceptance.EXPECTED_DELTA
    assert delta["preexisting_files"] == {
        "batch_manifest": {
            "changed": True,
            "destination": {
                "bytes": acceptance.DESTINATION_BATCH_PIN[0],
                "sha256": acceptance.DESTINATION_BATCH_PIN[1],
            },
            "path": "batch-manifest.json",
            "source": {
                "bytes": acceptance.SOURCE_BATCH_PIN[0],
                "sha256": acceptance.SOURCE_BATCH_PIN[1],
            },
        },
        "non_manifest_byte_identical": 13_436,
        "non_manifest_changed": [],
        "removed": [],
    }
    assert delta["files_added_count"] == len(delta["files_added"]) == 75
    assert delta["directories_added_count"] == len(delta["directories_added"]) == 50
    assert delta["directories_removed"] == []
    assert all(
        row["path"].startswith("jobs/satq-")
        and "/catalog/" in row["path"]
        and Path(row["path"]).name in acceptance.batch.CATALOG_FILES
        for row in delta["files_added"]
    )
    assert all(path.startswith("jobs/satq-") for path in delta["directories_added"])
    assert manifest["output"]["delta"] == acceptance.EXPECTED_DELTA


def test_bounded_outcomes_totals_and_next_pending_are_exact(
    accepted: tuple[dict[str, object], dict[str, object]],
) -> None:
    manifest, delta = accepted
    document = json.loads(
        (acceptance.DESTINATION / "batch-manifest.json").read_text(encoding="utf-8")
    )
    selected = sorted(
        (
            task
            for task in document["jobs"].values()
            if acceptance.POSITION_START
            <= task["queue_position"]
            <= acceptance.POSITION_END
        ),
        key=lambda task: task["queue_position"],
    )
    assert [task["queue_position"] for task in selected] == list(range(4_795, 4_820))
    assert Counter(task["state"] for task in selected) == Counter({"completed": 25})
    assert all(task["attempts"] == 1 and not task["failures"] for task in selected)
    assert all(task["selected_ids"] is not None for task in selected)
    assert document["last_run"] == acceptance.EXPECTED_RUN
    assert document["summary"] == acceptance.DESTINATION_SUMMARY
    assert manifest["output"]["summary"] == acceptance.DESTINATION_SUMMARY
    assert manifest["output"]["next_pending"] == {
        "queue_id": acceptance.NEXT_PENDING_QUEUE_ID,
        "queue_position": 4_820,
    }
    assert [row["queue_position"] for row in delta["queue_tasks"]] == list(
        range(4_795, 4_820)
    )


def test_modes_chronology_lock_and_scope_remain_fail_closed(
    accepted: tuple[dict[str, object], dict[str, object]],
) -> None:
    manifest, _delta = accepted
    for root in (acceptance.SOURCE, acceptance.DESTINATION, acceptance.OUTPUT):
        files, directories = acceptance.recovery._regular_tree(root, "sealed tree")
        assert all(stat.S_IMODE(path.stat().st_mode) == 0o444 for path in files)
        assert all(stat.S_IMODE(path.stat().st_mode) == 0o555 for path in directories)
    lock = acceptance.DESTINATION_LOCK
    assert not lock.is_symlink()
    assert lock.is_file()
    assert lock.stat().st_size == 0
    assert stat.S_IMODE(lock.stat().st_mode) == 0o600
    assert acceptance.DESTINATION not in lock.parents

    chronology = manifest["clone"]
    assert chronology["filesystem"] == "APFS"
    assert chronology["source_and_destination_same_device"] is True
    assert (
        chronology["source_root_chronology"]["device"]
        == (chronology["destination_root_chronology"]["device"])
    )
    assert (
        chronology["destination_root_chronology"]["birthtime"]
        < (manifest["output"]["lock"]["birthtime"])
    )
    assert (
        manifest["output"]["lock"]["birthtime"]
        < (manifest["execution"]["run"]["started_at"])
    )
    assert (
        manifest["execution"]["run"]["finished_at"]
        < (chronology["destination_root_chronology"]["ctime"])
    )
    assert (
        chronology["destination_root_chronology"]["ctime"] < (manifest["accepted_at"])
    )

    assert manifest["scope"] == acceptance.SCOPE
    assert manifest["builder"]["network_access"] is False
    assert manifest["execution"]["http_outcomes"] == {
        "actual_status_codes_persisted": False,
        "catalog_pair_selection_completed": 25,
        "http_attempts_reserved": 50,
        "provider_http_success_count_claimed": False,
        "provider_or_transport_failures_recorded": 0,
    }
    for name, value in manifest["scope"].items():
        if (
            name.startswith("imagery_")
            or name.endswith("_integration")
            or name
            in {
                "atlas_mutation",
                "automated_promotion_allowed",
                "change_analysis_executed",
                "global_completeness_claimed",
                "semianalysis_parity_claimed",
                "unique_site_claim_created",
            }
        ):
            assert value is False, name


def test_acceptance_builder_contains_no_network_or_inference_executor() -> None:
    source = inspect.getsource(acceptance)
    assert "subprocess" not in source
    assert "urlopen(" not in source
    assert "requests." not in source
    assert "socket." not in source
    assert "computer_vision(" not in source
    assert "promote_to_atlas" not in source
