from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import shutil

import pytest

try:
    from datacenter_atlas.datacenter_atlas import (
        merlin_cyrusone_beale_official_current_build_gap_v2_20260722 as tranche,
    )
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import (  # type: ignore[no-redef]
        merlin_cyrusone_beale_official_current_build_gap_v2_20260722 as tranche,
    )


def test_v1_incident_is_exactly_pinned_and_rejected() -> None:
    tranche._require_v1_lineage()
    lineage = tranche._incident_lineage()
    assert lineage["accepted_as_base"] is False
    assert lineage["status"] == "rejected_publication_incident"
    assert lineage["rejected_sentence"] == tranche.REJECTED_SENTENCE
    assert "500 MW to Tulsa County" in lineage["rejection_reason"]
    assert "600 MW to Pima County" in lineage["rejection_reason"]
    assert len(lineage["artifact_members"]) == 7
    assert len(lineage["source_files"]) == 6
    assert lineage["physical_tree_sha256"] == tranche.V1_PHYSICAL_TREE_SHA256
    assert lineage["logical_tree_sha256"] == tranche.V1_LOGICAL_TREE_SHA256


def test_v2_reuses_four_sources_and_corrects_two_noncolliding_files() -> None:
    documents = tranche.expected_source_documents()
    assert tuple(documents) == tranche.SOURCE_FILENAMES
    assert len(tranche.REUSED_SOURCE_FILENAMES) == 4
    assert len(tranche.NEW_SOURCE_FILENAMES) == 2
    predecessor = tranche.v1.expected_source_documents()
    for name in tranche.REUSED_SOURCE_FILENAMES:
        assert tranche._canonical(documents[name]) == tranche._canonical(predecessor[name])
        assert tranche._sha256_bytes(tranche._canonical(documents[name])) == (
            tranche.V1_SOURCE_PINS[name][1]
        )
    assert tranche.V2_TULSA_FILENAME not in predecessor
    assert tranche.V2_PIMA_FILENAME not in predecessor


def test_tulsa_500_and_pima_600_are_scoped_metadata_only() -> None:
    documents = tranche.expected_source_documents()
    tranche._assert_capacity_context(documents)
    tulsa = documents[tranche.V2_TULSA_FILENAME]
    pima = documents[tranche.V2_PIMA_FILENAME]
    assert tulsa["capacities"] == []
    assert pima["capacities"] == []
    assert "500 MW" in next(
        row
        for row in tulsa["evidence"]
        if row["key"] == tranche.TULSA_CONTEXT_KEY
    )["metadata"]["capacity_context_as_reported"]
    assert "600 MW" in next(
        row
        for row in pima["evidence"]
        if row["key"] == tranche.PIMA_CONTEXT_KEY
    )["metadata"]["capacity_context_as_reported"]
    assert tranche.REJECTED_SENTENCE not in json.dumps(pima, sort_keys=True)
    capacities = [row for document in documents.values() for row in document["capacities"]]
    assert sorted(row["base"] for row in capacities) == [18.0, 54.0]


def test_negative_guard_rejects_swapped_tulsa_and_pima_context() -> None:
    swapped = copy.deepcopy(tranche.expected_source_documents())
    tulsa = next(
        row
        for row in swapped[tranche.V2_TULSA_FILENAME]["evidence"]
        if row["key"] == tranche.TULSA_CONTEXT_KEY
    )
    pima = next(
        row
        for row in swapped[tranche.V2_PIMA_FILENAME]["evidence"]
        if row["key"] == tranche.PIMA_CONTEXT_KEY
    )
    tulsa["metadata"]["capacity_context_as_reported"], pima["metadata"][
        "capacity_context_as_reported"
    ] = (
        pima["metadata"]["capacity_context_as_reported"],
        tulsa["metadata"]["capacity_context_as_reported"],
    )
    with pytest.raises(RuntimeError, match="Tulsa must be 500 MW"):
        tranche._assert_capacity_context(swapped)


def test_v2_exact_counts_and_collision_boundary() -> None:
    documents = tranche.expected_source_documents()
    assert len(
        {
            document[entity]["stable_key"]
            for document in documents.values()
            for entity in ("campus", "project")
        }
    ) == 11
    assert len(
        {
            row["key"]
            for document in documents.values()
            for row in document["evidence"]
        }
    ) == 13
    assert sum(len(document["lifecycle"]) for document in documents.values()) == 8
    witness = tranche._collision_witness(documents)
    assert witness["exact_v92_stable_key_collisions"] == []
    assert witness["exact_v92_evidence_key_collisions"] == []
    assert witness["unexpected_source_collisions"] == {}
    assert witness["expected_v1_predecessor_overlap"]["stable_keys"] == 11


def test_private_v2_stage_replays_offline() -> None:
    if tranche.ARTIFACT.exists():
        assert tranche.validate_artifact()["new_source_records"] == 2
        return
    recorded_at = (
        datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=30)
    ).isoformat().replace("+00:00", "Z")
    prepared = tranche._prepare(recorded_at)
    try:
        manifest = tranche.validate_artifact(
            prepared.artifact_stage,
            source_paths=tranche._source_paths(prepared.source_stage),
            require_live=False,
            require_frozen=False,
            wall_clock=tranche._instant(recorded_at),
        )
        assert manifest["reused_source_records"] == 4
        assert manifest["new_source_records"] == 2
        snapshot = json.loads(
            (prepared.artifact_stage / "source-snapshot.json").read_text()
        )
        assert snapshot["totals"]["unique_evidence_records"] == 13
        assert snapshot["totals"]["distinct_entities"] == 11
        assert snapshot["correction_contract"]["both_untyped_metadata_only"] is True
        assert snapshot["correction_contract"]["normalized_capacity_rows_added_by_correction"] == 0
    finally:
        if prepared.source_stage.exists():
            shutil.rmtree(prepared.source_stage)
        if prepared.artifact_stage.exists():
            shutil.rmtree(prepared.artifact_stage)


def test_v2_late_collision_rolls_back_new_sources(tmp_path, monkeypatch) -> None:
    source_root = tmp_path / "sources"
    artifact_root = tmp_path / "artifacts"
    source_root.mkdir()
    artifact_root.mkdir()
    documents = tranche.expected_source_documents()
    source_stage = Path(tranche.tempfile.mkdtemp(dir=source_root))
    artifact_stage = Path(tranche.tempfile.mkdtemp(dir=artifact_root))
    tranche._write_source_stage(source_stage, documents)
    tranche._write_artifact_stage(
        artifact_stage, "2099-01-01T00:00:00Z", documents
    )
    monkeypatch.setattr(tranche, "SOURCES_ROOT", source_root)
    monkeypatch.setattr(tranche, "ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr(tranche, "ARTIFACT", artifact_root / tranche.ARTIFACT_ID)
    monkeypatch.setattr(tranche, "_freeze_after_barrier", lambda _prepared: None)
    prepared = tranche._Prepared(
        source_stage, artifact_stage, "2099-01-01T00:00:00Z"
    )
    original = tranche._promote_noreplace
    calls = 0

    def collide(source: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise FileExistsError("injected v2 collision")
        original(source, destination)

    monkeypatch.setattr(tranche, "_promote_noreplace", collide)
    try:
        with pytest.raises(FileExistsError, match="injected v2 collision"):
            tranche._publish(prepared)
        assert not any(source_root.glob("curated-*.json"))
        assert not tranche.ARTIFACT.exists()
    finally:
        if source_stage.exists():
            shutil.rmtree(source_stage)
        if artifact_stage.exists():
            shutil.rmtree(artifact_stage)


def test_v2_chronology_tamper_and_residue_after_publication(tmp_path) -> None:
    if not tranche.ARTIFACT.exists():
        pytest.skip("v2 artifact not published yet")
    manifest = tranche.validate_artifact()
    before = tranche._instant(manifest["recorded_at"]) - timedelta(microseconds=1)
    with pytest.raises(RuntimeError, match="recorded_at is not live"):
        tranche.validate_artifact(wall_clock=before)
    assert not tranche.PUBLICATION_LOCK.exists()
    assert not list(tranche.SOURCES_ROOT.glob(".merlin-cyrusone-beale-v2-sources.*"))
    assert not list(tranche.ARTIFACT_ROOT.glob(f".{tranche.ARTIFACT_ID}.*"))
    copied = tmp_path / "artifact"
    shutil.copytree(tranche.ARTIFACT, copied)
    copied.chmod(0o755)
    target = copied / "source-snapshot.json"
    target.chmod(0o644)
    target.write_bytes(target.read_bytes() + b" ")
    target.chmod(0o444)
    copied.chmod(0o555)
    with pytest.raises(RuntimeError, match="manifest pin differs"):
        tranche.validate_artifact(copied)
