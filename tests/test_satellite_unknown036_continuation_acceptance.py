from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
import hashlib
import inspect
import json
from pathlib import Path
import stat

import pytest

from datacenter_atlas import (
    satellite_unknown036_continuation_acceptance as acceptance,
)


MANIFEST_SHA256 = "fed0d7d0176af0eda611f7c1a403b827e85db892eac00114eae35451ee2a1088"
DELTA_SHA256 = "81aa4633666db22c8d5c4bdb6ca7ceab1bbd6524ff0a812a238480916781070a"


@pytest.fixture(scope="module")
def built() -> tuple[dict[str, bytes], dict[str, object], dict[str, object]]:
    files = acceptance.build_unknown036_continuation_acceptance()
    manifest = json.loads(files[acceptance.MANIFEST_FILENAME])
    delta = json.loads(files[acceptance.DELTA_FILENAME])
    return files, manifest, delta


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _inventory_rows(raw: bytes) -> list[tuple[str, int, str]]:
    rows: list[tuple[str, int, str]] = []
    for line in raw.splitlines():
        path, size, digest = line.decode("utf-8").split("\0")
        rows.append((path, int(size), digest))
    return rows


def test_manifest_is_canonical_closed_and_hash_binds_every_input(
    built: tuple[dict[str, bytes], dict[str, object], dict[str, object]],
) -> None:
    files, manifest, _delta = built
    manifest_raw = files[acceptance.MANIFEST_FILENAME]
    digest = _sha256(manifest_raw)
    assert digest == MANIFEST_SHA256
    assert manifest_raw == acceptance._canonical_json(manifest)
    assert files[acceptance.SIDECAR_FILENAME] == (
        f"{digest}  {acceptance.MANIFEST_FILENAME}\n".encode("ascii")
    )
    assert set(files) == acceptance.CLOSED_FILENAMES
    assert manifest["artifact_id"] == acceptance.ARTIFACT_ID
    assert manifest["accepted_at"] == acceptance.ACCEPTED_AT
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


def test_complete_inventories_and_clone_delta_are_exact(
    built: tuple[dict[str, bytes], dict[str, object], dict[str, object]],
) -> None:
    files, manifest, delta = built
    assert _sha256(files[acceptance.DELTA_FILENAME]) == DELTA_SHA256
    source_rows = _inventory_rows(files[acceptance.SOURCE_INVENTORY_FILENAME])
    destination_rows = _inventory_rows(files[acceptance.DESTINATION_INVENTORY_FILENAME])
    assert len(source_rows) == acceptance.SOURCE_INVENTORY["files"] == 13_512
    assert len(destination_rows) == acceptance.DESTINATION_INVENTORY["files"] == 13_584
    assert sum(row[1] for row in source_rows) == 3_120_154_596
    assert sum(row[1] for row in destination_rows) == 3_132_875_874
    assert (
        _sha256(files[acceptance.SOURCE_INVENTORY_FILENAME])
        == (acceptance.SOURCE_INVENTORY["sha256"])
    )
    assert (
        _sha256(files[acceptance.DESTINATION_INVENTORY_FILENAME])
        == (acceptance.DESTINATION_INVENTORY["sha256"])
    )
    assert manifest["source_continuation"]["inventory"] == (acceptance.SOURCE_INVENTORY)
    assert manifest["output"]["inventory"] == acceptance.DESTINATION_INVENTORY
    assert [row[0] for row in source_rows] == sorted(row[0] for row in source_rows)
    assert [row[0] for row in destination_rows] == sorted(
        row[0] for row in destination_rows
    )

    assert delta["summary"] == acceptance.EXPECTED_DELTA
    assert delta["files_added_count"] == len(delta["files_added"]) == 72
    assert delta["directories_added_count"] == len(delta["directories_added"]) == 49
    assert delta["directories_removed"] == []
    assert delta["preexisting_files"]["non_manifest_byte_identical"] == 13_511
    assert delta["preexisting_files"]["non_manifest_changed"] == []
    assert delta["preexisting_files"]["removed"] == []
    assert all(
        row["path"].startswith("jobs/satq-")
        and "/catalog/" in row["path"]
        and Path(row["path"]).name in acceptance.batch.CATALOG_FILES
        for row in delta["files_added"]
    )


def test_bounded_outcomes_no_scene_and_next_pending_are_exact(
    built: tuple[dict[str, bytes], dict[str, object], dict[str, object]],
) -> None:
    _files, manifest, delta = built
    document = json.loads(
        (acceptance.DESTINATION / "batch-manifest.json").read_text(encoding="utf-8")
    )
    selected = sorted(
        (
            (queue_id, task)
            for queue_id, task in document["jobs"].items()
            if acceptance.POSITION_START
            <= task["queue_position"]
            <= acceptance.POSITION_END
        ),
        key=lambda item: item[1]["queue_position"],
    )
    assert [task["queue_position"] for _queue_id, task in selected] == list(
        range(4_820, 4_845)
    )
    assert Counter(task["state"] for _queue_id, task in selected) == Counter(
        {"completed": 24, acceptance.batch.UNAVAILABLE_NO_SCENE: 1}
    )
    no_scene = [item for item in selected if item[1]["state"] != "completed"]
    assert len(no_scene) == 1
    assert no_scene[0][0] == acceptance.NO_SCENE_QUEUE_ID
    assert no_scene[0][1]["unavailability"] == acceptance.EXPECTED_UNAVAILABILITY
    assert document["last_run"] == acceptance.EXPECTED_RUN
    assert document["summary"] == acceptance.DESTINATION_SUMMARY
    assert manifest["output"]["summary"] == acceptance.DESTINATION_SUMMARY
    assert manifest["output"]["next_pending"] == {
        "queue_id": acceptance.NEXT_PENDING_QUEUE_ID,
        "queue_position": 4_845,
    }
    assert [row["queue_position"] for row in delta["queue_tasks"]] == list(
        range(4_820, 4_845)
    )


def test_modes_clone_chronology_and_scope_remain_fail_closed(
    built: tuple[dict[str, bytes], dict[str, object], dict[str, object]],
) -> None:
    _files, manifest, _delta = built
    for root in (acceptance.SOURCE, acceptance.DESTINATION):
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
        == chronology["destination_root_chronology"]["device"]
    )
    assert (
        chronology["destination_root_chronology"]["birthtime"]
        < manifest["output"]["lock"]["birthtime"]
        < manifest["execution"]["run"]["started_at"]
        < manifest["execution"]["run"]["finished_at"]
        < chronology["destination_root_chronology"]["ctime"]
        < manifest["accepted_at"]
    )

    assert manifest["scope"] == acceptance.SCOPE
    assert manifest["builder"]["network_access"] is False
    assert manifest["execution"]["http_outcomes"] == {
        "actual_status_codes_persisted": False,
        "catalog_pair_selection_completed": 24,
        "http_attempts_reserved": 50,
        "no_scene_outcomes_persisted": 1,
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


def test_acceptance_is_offline_and_final_wrapper_is_governed_if_present(
    built: tuple[dict[str, bytes], dict[str, object], dict[str, object]],
) -> None:
    files, _manifest, _delta = built
    source = inspect.getsource(acceptance)
    assert "subprocess" not in source
    assert "urlopen(" not in source
    assert "requests." not in source
    assert "socket." not in source
    assert "computer_vision(" not in source
    assert "promote_to_atlas" not in source
    if acceptance.OUTPUT.exists():
        acceptance._closed_tree(acceptance.OUTPUT, files)
        acceptance._validate_publication_chronology(acceptance.OUTPUT)
    else:
        assert datetime.now(UTC) < acceptance._timestamp(
            acceptance.ACCEPTED_AT, "accepted_at"
        )
