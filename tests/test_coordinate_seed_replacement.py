from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from datacenter_atlas.coordinate_seed_replacement import (
    CoordinateReplacement,
    replace_curated_inputs,
)


ROOT = Path(__file__).resolve().parents[1]
PREDECESSOR = (
    "sources/curated-official-2026-07-21-scala-sscllp01-lampa-current-build.json"
)
REJECTED_V2_SUCCESSOR = (
    "source_artifacts/site-coordinate-assessment-2026-07-21-v2/"
    "normalized-successors/curated-official-2026-07-21-scala-sscllp01-"
    "lampa-current-build-coordinate-v2.json"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(document: object) -> bytes:
    return (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode()


class CoordinateSeedReplacementTests(unittest.TestCase):
    def _specification(self, successor: Path) -> CoordinateReplacement:
        document = json.loads(successor.read_text(encoding="utf-8"))
        return CoordinateReplacement(
            predecessor_path=PREDECESSOR,
            predecessor_sha256=sha256(ROOT / PREDECESSOR),
            successor_path=successor.relative_to(ROOT).as_posix(),
            successor_bytes=successor.stat().st_size,
            successor_sha256=sha256(successor),
            campus_key="curated:scala-lampa-campus",
            project_key="curated:scala-lampa-campus:sscllp01",
            added_evidence_key=document["evidence"][-1]["key"],
        )

    def test_rejected_v2_future_retrieval_cannot_seed_a_release(self) -> None:
        successor = ROOT / REJECTED_V2_SUCCESSOR
        specification = self._specification(successor)
        rows = [{"path": PREDECESSOR, "sha256": sha256(ROOT / PREDECESSOR)}]
        wall_clock = datetime(2026, 7, 21, 9, 50, tzinfo=timezone.utc)
        with self.assertRaisesRegex(
            ValueError,
            "source evidence retrieved_at is later than release recorded_at",
        ):
            replace_curated_inputs(
                ROOT,
                rows,
                (specification,),
                recorded_at="2026-07-21T09:50:00Z",
                validation_wall_clock=wall_clock,
            )

    def test_release_recorded_at_cannot_exceed_current_build_time(self) -> None:
        successor = ROOT / REJECTED_V2_SUCCESSOR
        specification = self._specification(successor)
        rows = [{"path": PREDECESSOR, "sha256": sha256(ROOT / PREDECESSOR)}]
        with self.assertRaisesRegex(ValueError, "later than the current build time"):
            replace_curated_inputs(
                ROOT,
                rows,
                (specification,),
                recorded_at="2026-07-21T18:00:00Z",
                validation_wall_clock=datetime(
                    2026, 7, 21, 9, 50, tzinfo=timezone.utc
                ),
            )

    def test_exact_one_for_one_coordinate_replacement_preserves_order(self) -> None:
        predecessor = json.loads((ROOT / PREDECESSOR).read_text(encoding="utf-8"))
        rejected_successor = json.loads(
            (ROOT / REJECTED_V2_SUCCESSOR).read_text(encoding="utf-8")
        )
        successor = copy.deepcopy(rejected_successor)
        successor["evidence"][-1]["retrieved_at"] = "2026-07-21T09:49:00Z"
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            predecessor_path = temporary_root / PREDECESSOR
            successor_relative = "artifact/normalized-successors/lampa.json"
            successor_path = temporary_root / successor_relative
            predecessor_path.parent.mkdir(parents=True)
            successor_path.parent.mkdir(parents=True)
            predecessor_path.write_bytes(canonical(predecessor))
            successor_path.write_bytes(canonical(successor))
            predecessor_path.chmod(0o644)
            successor_path.chmod(0o444)
            specification = CoordinateReplacement(
                predecessor_path=PREDECESSOR,
                predecessor_sha256=sha256(predecessor_path),
                successor_path=successor_relative,
                successor_bytes=successor_path.stat().st_size,
                successor_sha256=sha256(successor_path),
                campus_key="curated:scala-lampa-campus",
                project_key="curated:scala-lampa-campus:sscllp01",
                added_evidence_key=successor["evidence"][-1]["key"],
            )
            rows = [
                {"path": PREDECESSOR, "sha256": sha256(predecessor_path)},
            ]
            selected, paths = replace_curated_inputs(
                temporary_root,
                rows,
                (specification,),
                recorded_at="2026-07-21T09:50:00Z",
                validation_wall_clock=datetime(
                    2026, 7, 21, 9, 50, tzinfo=timezone.utc
                ),
            )
            self.assertEqual(
                selected,
                [{"path": successor_relative, "sha256": sha256(successor_path)}],
            )
            self.assertEqual(paths, [successor_path])

    def test_full_v69_inventory_preserves_legacy_bytes_and_replaces_three_rows(self) -> None:
        definition = json.loads(
            (ROOT / "sources/open-seed-2026-07-21-v69.json").read_text(
                encoding="utf-8"
            )
        )
        artifact = ROOT / "source_artifacts/site-coordinate-assessment-2026-07-21-v3"
        disposition = json.loads(
            (artifact / "disposition.json").read_text(encoding="utf-8")
        )
        specifications = []
        for row in disposition["accepted"]["successors"].values():
            successor = artifact / row["path"]
            document = json.loads(successor.read_text(encoding="utf-8"))
            predecessor = ROOT / row["predecessor"]
            specifications.append(
                CoordinateReplacement(
                    predecessor_path=row["predecessor"],
                    predecessor_sha256=sha256(predecessor),
                    successor_path=successor.relative_to(ROOT).as_posix(),
                    successor_bytes=row["bytes"],
                    successor_sha256=row["sha256"],
                    campus_key=row["campus_key"],
                    project_key=row["project_key"],
                    added_evidence_key=document["evidence"][-1]["key"],
                )
            )

        now = datetime.now(timezone.utc)
        selected, paths = replace_curated_inputs(
            ROOT,
            definition["curated_inputs"],
            specifications,
            recorded_at=now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            validation_wall_clock=now,
        )
        self.assertEqual((len(selected), len(paths)), (391, 391))
        selected_paths = [row["path"] for row in selected]
        base_paths = [row["path"] for row in definition["curated_inputs"]]
        for row in specifications:
            self.assertEqual(
                selected_paths.index(row.successor_path),
                base_paths.index(row.predecessor_path),
            )
        self.assertTrue(
            all(row.predecessor_path not in selected_paths for row in specifications)
        )
        self.assertTrue(
            all(row.successor_path in selected_paths for row in specifications)
        )
        legacy = "sources/curated-official-2026-07-17-childress.json"
        self.assertIn(legacy, selected_paths)
        legacy_row = selected[selected_paths.index(legacy)]
        self.assertEqual(legacy_row, definition["curated_inputs"][selected_paths.index(legacy)])

    def test_coexistence_and_non_coordinate_mutation_fail_closed(self) -> None:
        successor = ROOT / REJECTED_V2_SUCCESSOR
        specification = self._specification(successor)
        rows = [
            {"path": PREDECESSOR, "sha256": sha256(ROOT / PREDECESSOR)},
            {
                "path": REJECTED_V2_SUCCESSOR,
                "sha256": sha256(successor),
            },
        ]
        with self.assertRaisesRegex(ValueError, "coexist"):
            replace_curated_inputs(
                ROOT,
                rows,
                (specification,),
                recorded_at="2026-07-21T18:00:00Z",
                validation_wall_clock=datetime(
                    2026, 7, 21, 18, 0, tzinfo=timezone.utc
                ),
            )

        mutated = json.loads(successor.read_text(encoding="utf-8"))
        mutated["capacities"][0]["base"] += 1
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            predecessor_path = temporary_root / PREDECESSOR
            successor_relative = "artifact/normalized-successors/lampa.json"
            successor_path = temporary_root / successor_relative
            predecessor_path.parent.mkdir(parents=True)
            successor_path.parent.mkdir(parents=True)
            predecessor_path.write_bytes((ROOT / PREDECESSOR).read_bytes())
            successor_path.write_bytes(canonical(mutated))
            predecessor_path.chmod(0o644)
            successor_path.chmod(0o444)
            altered = CoordinateReplacement(
                predecessor_path=PREDECESSOR,
                predecessor_sha256=sha256(predecessor_path),
                successor_path=successor_relative,
                successor_bytes=successor_path.stat().st_size,
                successor_sha256=sha256(successor_path),
                campus_key=specification.campus_key,
                project_key=specification.project_key,
                added_evidence_key=specification.added_evidence_key,
            )
            with self.assertRaisesRegex(ValueError, "non-coordinate claim delta"):
                replace_curated_inputs(
                    temporary_root,
                    [{"path": PREDECESSOR, "sha256": sha256(predecessor_path)}],
                    (altered,),
                    recorded_at="2026-07-21T18:00:00Z",
                    validation_wall_clock=datetime(
                        2026, 7, 21, 18, 0, tzinfo=timezone.utc
                    ),
                )


if __name__ == "__main__":
    unittest.main()
