# Algorithm-v2 calibration re-review preparation

The preparation builder performs a strict identity join from all 43 historical algorithm-v1 review inputs to completed algorithm-v2 outputs in the pinned frozen change runs. Exact correspondence requires the queue ID, entity ID, AOI, and both STAC item hashes to match. AOI-only and scene-pair-only coincidences are recorded but never substituted.

The generated preparation queue contains no earlier decisions, outcomes, review paths, or historical queue IDs. At publication time all 43 rows were blocked because the then-frozen algorithm-v2 runs contained zero exact outputs. That historical state remains immutable. A later bounded rerun executed every specification under the pinned numerical runtime: 36 produced exact outputs and seven stopped at the explicit single-asset boundary requiring a multi-tile mosaic. The separate [label-blind numerical aggregate](satellite_calibration_aggregate.md) binds that 43-row partition without importing the sealed labels. Neither artifact is a completed re-review or algorithm-v2 calibration.

`rerun-specs.jsonl` provides one executable, operator-facing rerun specification per historical identity. It binds the original queue, entity, AOI, selected scene IDs and canonical STAC feature hashes, source catalog response and manifest checkpoints, processor code hashes, and the exact argument vector. It contains no prior analyst label. The runner validates all 43 specifications without opening imagery when invoked with `--validate-inputs-only`; numerical execution is a separate explicit mode. On execution, it hash-verifies private copies of each input and runs a self-contained snapshot of the bound processor files before atomically publishing an immutable shard.

Earlier analyst provenance is stored separately at `sealed/lineage.jsonl`, with mode `0400` under a mode `0500` directory. It is intended only for a post-review join. These modes are an operational guard, not encryption.

Build once:

```bash
python3 scripts/build_satellite_calibration_rereview.py \
  --definition sources/satellite-calibration-rereview-2026-07-19-algorithm-v2-preparation-v1.json \
  --output satellite_calibration_rereview/2026-07-19-algorithm-v2-preparation-v1
```

Reproduce and validate offline:

```bash
python3 scripts/build_satellite_calibration_rereview.py \
  --validate-only \
  --definition sources/satellite-calibration-rereview-2026-07-19-algorithm-v2-preparation-v1.json \
  --output satellite_calibration_rereview/2026-07-19-algorithm-v2-preparation-v1
```

Validation rejects extra files, symlinks, mode drift, altered inputs, altered release bytes, label-bearing reviewer rows, differing v2 processor hashes, duplicate output identities, and any partial-key substitution.

Validate all rerun inputs without numerical execution:

```bash
python3 scripts/run_satellite_calibration_reruns.py \
  --validate-inputs-only \
  --preparation-dir satellite_calibration_rereview/2026-07-19-algorithm-v2-preparation-v1 \
  --definition sources/satellite-calibration-rereview-2026-07-19-algorithm-v2-preparation-v1.json
```

Execute only after that gate, always to a new path and under the exact established numerical runtime. The runner records Python, platform, zlib, NumPy, Pillow, rasterio, GDAL, and PROJ versions; requires the pinned versions before staging; rechecks them before every job and before publication; and invokes the frozen processor snapshot with `-B` and `PYTHONDONTWRITEBYTECODE=1`. This example selects one item:

```bash
uv run --python 3.12 \
  --with numpy==2.5.1 --with pillow==12.3.0 --with rasterio==1.5.0 \
  python scripts/run_satellite_calibration_reruns.py \
  --preparation-dir satellite_calibration_rereview/2026-07-19-algorithm-v2-preparation-v1 \
  --definition sources/satellite-calibration-rereview-2026-07-19-algorithm-v2-preparation-v1.json \
  --output-dir satellite_calibration_reruns/2026-07-19-v2-rerun-shard-000 \
  --start-index 0 \
  --max-jobs 1
```

Validate any completed or failure-bearing immutable shard offline under the same pinned runtime:

```bash
uv run --python 3.12 \
  --with numpy==2.5.1 --with pillow==12.3.0 --with rasterio==1.5.0 \
  python scripts/run_satellite_calibration_reruns.py \
  --validate-only \
  --preparation-dir satellite_calibration_rereview/2026-07-19-algorithm-v2-preparation-v1 \
  --definition sources/satellite-calibration-rereview-2026-07-19-algorithm-v2-preparation-v1.json \
  --output-dir satellite_calibration_reruns/2026-07-19-v2-rerun-shard-000
```
