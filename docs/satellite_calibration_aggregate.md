# Label-blind algorithm-v2 numerical aggregate

This stage binds exactly ten immutable numerical rerun shards to the 43 public rerun specifications in the frozen algorithm-v2 preparation. It deliberately does not invoke the preparation validator because that validator opens the permission-sealed historical lineage. The aggregate reads only `manifest.json`, `manifest.sha256`, and `rerun-specs.jsonl` from the preparation; it never opens `sealed/lineage.jsonl` or any historical analyst review.

The release has three reviewer-safe data files:

- `numerical-inventory.jsonl` accounts for all 43 specifications exactly once.
- `reviewer-queue.jsonl` exposes only successful algorithm-v2 outputs and their immutable artifact checkpoints.
- `blocked-multitile.jsonl` explicitly records numerical jobs whose AOI crossed a scene asset and therefore requires a future multi-tile mosaic.

Historical queue IDs, historical identity hashes, retain/reject labels, outcomes, and analyst decisions are excluded from every reviewer-facing row. The output is numerical evidence awaiting blind review, not an adjudication and not algorithm-v2 calibration.

The source definition pins the preparation manifest/specs plus each shard manifest and sidecar by path, byte count, SHA-256, and mode. Validation reconstructs every output byte from those sources; validates exact schemas, canonical JSON/JSONL, sidecars, the 43-spec non-overlapping partition, current pinned runtime, frozen processor snapshots, report/GeoJSON/PNG semantics, artifact hashes, closed trees, modes, symlink absence, and source/output path separation; and rejects any failure that is not the explicit multi-tile boundary failure.

Create the immutable source definition once, with all ten `--shard-dir` arguments:

```bash
uv run --python 3.12 \
  --with numpy==2.5.1 --with pillow==12.3.0 --with rasterio==1.5.0 \
  python scripts/build_satellite_calibration_aggregate.py \
  --write-definition \
  --definition sources/satellite-calibration-v2-aggregate-2026-07-19-v1.json \
  --preparation-dir satellite_calibration_rereview/2026-07-19-algorithm-v2-preparation-v1 \
  --release-id algorithm-v2-numerical-aggregate-2026-07-19-v1 \
  --shard-dir satellite_calibration_reruns/2026-07-19-v2-rerun-shard-000 \
  --shard-dir satellite_calibration_reruns/2026-07-19-v2-rerun-shard-001 \
  --shard-dir satellite_calibration_reruns/2026-07-19-v2-rerun-shard-002 \
  --shard-dir satellite_calibration_reruns/2026-07-19-v2-rerun-shard-003 \
  --shard-dir satellite_calibration_reruns/2026-07-19-v2-rerun-shard-004 \
  --shard-dir satellite_calibration_reruns/2026-07-19-v2-rerun-shard-005 \
  --shard-dir satellite_calibration_reruns/2026-07-19-v2-rerun-shard-006 \
  --shard-dir satellite_calibration_reruns/2026-07-19-v2-rerun-shard-007 \
  --shard-dir satellite_calibration_reruns/2026-07-19-v2-rerun-shard-008 \
  --shard-dir satellite_calibration_reruns/2026-07-19-v2-rerun-shard-009
```

Build to a new path. Publication is staged, fsynced, frozen to `0555`/`0444`, validated offline, and then atomically renamed:

```bash
uv run --python 3.12 \
  --with numpy==2.5.1 --with pillow==12.3.0 --with rasterio==1.5.0 \
  python scripts/build_satellite_calibration_aggregate.py \
  --definition sources/satellite-calibration-v2-aggregate-2026-07-19-v1.json \
  --output-dir satellite_calibration_rereview/2026-07-19-algorithm-v2-numerical-aggregate-v1
```

Revalidate without network access under the same pinned runtime:

```bash
uv run --python 3.12 \
  --with numpy==2.5.1 --with pillow==12.3.0 --with rasterio==1.5.0 \
  python scripts/build_satellite_calibration_aggregate.py \
  --validate-only \
  --definition sources/satellite-calibration-v2-aggregate-2026-07-19-v1.json \
  --output-dir satellite_calibration_rereview/2026-07-19-algorithm-v2-numerical-aggregate-v1
```
