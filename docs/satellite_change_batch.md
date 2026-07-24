# Resumable satellite change-analysis batch

`scripts/run_satellite_change_batch.py` is the bounded execution step between a validated catalog
batch and analyst review. It accepts only catalog tasks already checkpointed as `completed`, resolves
the queue's exact `change_job_template`, and runs `sentinel_change.py` sequentially. Its outputs are
visible-change proposals. They do not create or alter an atlas identity, operator, lifecycle,
operating-status, data-centre type, IT-capacity, PUE, workload, power, or energy claim.

The change-run directory must be separate from both the immutable queue and every catalog-run
directory. Existing historical `jobs/<queue-id>/change/` directories beside catalog outputs are not
read, adopted, copied, or overwritten. A first run also has no implicit “first N” selection: it must
name queue IDs explicitly or supply a canonical exclusion file. Effective jobs are always restored to
immutable queue order before execution.

## Frozen five-job v2 qualification

The current active catalog batch has 65 completed scene pairs. Seven of those queue IDs have
historical reviewed algorithm-v1 outputs bound by calibration v4 and candidate fusion; they are not
current v2 outputs. The following five
explicit IDs are the queue-ordered v2 qualification set. The preserved
`2026-07-18-global-open-v3-active-unreviewed-001` checkpoint used algorithm v1: four jobs completed
and one failed output validation because a projected read-envelope edge leaked beyond the queue AOI.
Its manifest SHA-256 is
`f0e5bd0496bddbefebe30a4402999ceb2e987d4eaa2869e2b769b552edea4c01`. It remains frozen,
incomplete evidence and must not be resumed, renamed, or mixed with v2 output. The command below
produced the separate v2 `002` qualification bundle.

Run from `datacenter_atlas/`:

```sh
uv run --python 3.12 \
  --with numpy==2.5.1 --with pillow==12.3.0 --with rasterio==1.5.0 \
  python scripts/run_satellite_change_batch.py \
  --queue-dir satellite_review_queues/2026-07-18-global-open-v3 \
  --catalog-batch-dir satellite_review_runs/2026-07-18-global-open-v3-active-001 \
  --output-dir satellite_change_runs/2026-07-18-global-open-v3-active-unreviewed-002 \
  --queue-id satq-9e1d2b4c11c8f416b4c8eea8 \
  --queue-id satq-0415838405650334018145ec \
  --queue-id satq-fddd4db6778876be9e76cc4c \
  --queue-id satq-18542a69413d3f8a7d012ea9 \
  --queue-id satq-51c83c399743270854947aea \
  --max-jobs 5
```

The run completed all five selected jobs in one bounded invocation from
`2026-07-19T06:52:25Z` through `2026-07-19T06:52:55Z`, with zero failures, retries,
interruptions, or recovered publications. It is frozen at directory mode `0555` and file mode
`0444`. Its manifest SHA-256 is
`e435666a7148f8dfb24bbd037aeb3555bb59caa5571bdf138b50471e64ff2d78`.

| Queue ID | Source observation label | Valid AOI fraction | Components | Filtered proposal area | Report SHA-256 |
| --- | --- | ---: | ---: | ---: | --- |
| `satq-9e1d2b4c11c8f416b4c8eea8` | OpenStreetMap way 1194169753 | 31.84% | 13 | 151,300 m² | `e37a2a6d7973521ed573f89b16bd37d2cf9cb38ccef4fbd72a2f12265fd1923a` |
| `satq-0415838405650334018145ec` | OpenStreetMap way 1194169753 development project | 31.84% | 13 | 151,300 m² | `57fc2e8f8f0a2b42bdb1b3038cb6112978ebf1f7cd74a3a899c52205ab654550` |
| `satq-fddd4db6778876be9e76cc4c` | Google datacenter | 99.20% | 20 | 1,342,500 m² | `67013264ae91fcf38c9f91197de396e7433590703c0bbb11887ab15686470ead` |
| `satq-18542a69413d3f8a7d012ea9` | CyrusOne Datacenter development project | 100.00% | 34 | 920,700 m² | `6509a844adf5c3e6575f9654faefabfe35b0bb0ce7eecf066374dbbcf94d19bf` |
| `satq-51c83c399743270854947aea` | OpenStreetMap way 1288894120 development project | 98.73% | 20 | 1,331,600 m² | `144cf712e88d77de4bb2fe462a95359be0ce8df32576c3dc78f24b4973e7ed15` |

All five comparison PNGs received visual inspection, but no analyst decision artifact was created.
The two Virginia rows share the same AOI and byte-identical comparison PNG; they are not two site
observations. The two South Carolina AOIs overlap and highlight both a large new complex and other
surface changes. The Texas view contains extensive ordinary residential, road, and land change in
addition to industrial surfaces. These remain five machine proposal bundles, not five sites,
construction confirmations, lifecycle events, or accepted review labels. They do not enter the
construction master, map, current-coverage ledger, or calibration set.

## Active-lane v2 scale checkpoints

Three subsequent immutable checkpoints expanded current-v2 processing without treating proposals
as analyst decisions or sites:

| Run | State | Complete | Failed | Pending | Manifest SHA-256 |
| --- | --- | ---: | ---: | ---: | --- |
| `002` | Completed qualification | 5 | 0 | 0 | `e435666a7148f8dfb24bbd037aeb3555bb59caa5571bdf138b50471e64ff2d78` |
| `003` | Frozen incomplete; do not resume | 8 | 2 | 43 | `acd0a7ffaaff44b739a16e8f8ec3a334f9a5d11691b4b53c61244adac3db6e00` |
| `004` | Frozen incomplete; do not resume | 9 | 1 | 33 | `8876487ac5582d975a64d81c9022a3f49d94085982d5722f8ff2b90adc66a9e5` |
| `005` | Completed safe tranche | 21 | 0 | 0 | `7b150cbe75cd051744f694189f9ced4fde30408d5c7924cc3911a985e450167f` |

Across `002` through `005`, the completed inventory is 43 unique active-lane queue rows across 31
exact AOI geometries. All 43 are unreviewed machine proposals outside the construction master, map,
current ledger, candidate fusion, and historical calibration. The 003 and 004 failures are retained
fail-closed evidence that the originally selected single asset did not cover its required native
read window; they are not no-scene outcomes and their checkpoints must not be resumed.

At the end of these four checkpoints, 43 of the 65 active catalog completions had a current-v2
proposal. The other 22 rows were tracked as seven historical reviewed-v1 rows and 15 rows without a
change output. These were workflow states, not additive sites. The later coverage-aware reselection
below changed that accounting without mutating any of these frozen checkpoints. “Full-cover” means
only that selected assets cover every required native read window and interpolation halo; cloud,
shadow, and nodata can still reduce valid-pixel coverage.

The first checkpoint records the actual Python, NumPy, Pillow, and rasterio versions resolved by
`uv`; OS, architecture, zlib, and available GDAL/PROJ runtime versions; and exact hashes of the
change runner, change processor, catalog-batch, queue, catalog, model, and CLI source files. Resume
under the same runtime. If `uv` later resolves a different package version, the runner stops before
another job; use the versions recorded in `processor.runtime` to pin the resume command exactly
rather than editing the checkpoint.

## Coverage-aware edge reselection and bounded rerun

The frozen reselection release
`satellite_catalog_reselection_runs/2026-07-19-global-open-v3-active-edge-reselection-001`
re-evaluates the preserved active-001 provider responses without making new catalog requests. It
selects full-cover alternate scene pairs for 15 queue rows across nine exact AOIs. Two additional
France rows sharing one AOI have no full-cover baseline scene in their archived responses and remain
explicitly unresolved pending a supplemental same-datatake tile or a separately versioned multi-tile
processor. The release made zero imagery-pixel reads and executed zero change jobs. Its manifest
SHA-256 is
`0c6a6199af89c5e4c2e21d8e518c5b06071b06659e223e22642600c297fc06a7`.

The separate change run
`satellite_change_runs/2026-07-19-global-open-v3-active-edge-reselected-001` executed the 15 supported
jobs in three bounded five-job invocations. All 15 completed on their first attempt; failures,
interruptions, and pending jobs are zero. The run is frozen with 91 files at mode `0444` and 32
directories at mode `0555`. Offline validation against the exact queue, active catalog, reselection
release, processor, and recorded numerical runtime passes. Its manifest SHA-256 is
`6932ed40ccdc4650336a3d0716e2ab73aee09f10f1381dc6e8811e4aaf5dbc91`; the ordered,
path-bound full-tree digest is
`4220cc8f840166469a2d0264776da1e838d61ec5c4279c68887186025e4b5876`.

All nine distinct comparison views received visual QA. The masks include water and cloud/no-data
boundaries, agricultural or seasonal change, ordinary urban and port surfaces, and industrial-roof
change. No analyst decision artifact was created, so every row remains an unreviewed visible-change
proposal. The run performs no Atlas mutation and makes no identity, operator, lifecycle, status,
type, capacity, power, PUE, workload, or energy inference.

After this run, 58 of the 65 active catalog rows have current-v2 proposals across 40 exact AOIs.
Seven active rows also have historical reviewed-v1 evidence; two of those seven now overlap the
current-v2 set. Their reselected v2 scene hashes differ from the historical-v1 scene hashes, so the
old decisions cannot be transferred. Seven active rows still lack current-v2 output: five retain
historical-v1 evidence only and the two France rows have neither a current-v2 output nor a
historical-v1 review. These sets are evidence-accounting units, not unique sites or calibration
labels.

## Selection contract

Repeated `--queue-id` arguments form an explicit inclusion. Every ID must exist in the verified queue
and have a completed task in one of the supplied catalog batches. The manifest copies the canonical
queue-ordered list and separately reports:

- completed catalog jobs selected;
- completed catalog jobs omitted by the explicit inclusion;
- completed catalog jobs excluded by an exclusion file; and
- exclusion IDs that do not have a completed catalog input in the supplied batches.

For a reusable exclusion, provide canonical pretty JSON with the exact queue-manifest SHA-256 and IDs
in queue order:

```json
{
  "purpose": "satellite_change_batch_exclusions",
  "queue_ids": [
    "satq-example"
  ],
  "queue_manifest_sha256": "<64 lowercase hex characters>",
  "schema_version": 1
}
```

Pass it with `--exclusion-file reviewed-change-ids.json`. Its exact bytes and SHA-256 are copied into
the change manifest. The effective ID inventory is copied as well, so resumption does not depend on a
mutable external pathname. Supplying an exclusion file again on validation or resume requires the
same effective selection and exact source lineage.

The three active-lane exclusion checkpoints and their non-success meanings are documented in
[`satellite_change_selections/README.md`](../satellite_change_selections/README.md).

Multiple `--catalog-batch-dir` arguments are allowed only when their completed queue-ID inventories do
not overlap. Ambiguous duplicate completed inputs are rejected rather than selected by pathname or
argument order.

## Atomic output and interruption contract

Before any subprocess starts, the runner offline-validates the complete queue bundle and every catalog
batch, including every terminal catalog output. It accepts only an `earth-search-v1` queue and rejects
every required selected asset URL unless it is HTTPS on
`sentinel-cogs.s3.us-west-2.amazonaws.com`, below `/sentinel-s2-l2a-cogs/`, with no credentials,
port, query, fragment, encoded path, or traversal. It binds the exact queue and catalog manifests,
catalog task hashes, selected scene IDs, catalog file hashes, resolved template arguments, processor
files, numerical runtime, configuration, and selection into canonical `batch-manifest.json`.

Execution holds a non-blocking exclusive OS lock on the opened output-directory file descriptor from
checkpoint inspection through final validation. A concurrent executor fails before it can invoke a
command or mutate the checkpoint. Offline validation takes a non-blocking shared lock and fails safely
while an executor owns the directory. The lock creates no file inside the closed output tree.

Each attempt is checkpointed as `running` before invocation. `sentinel_change.py` writes to
`jobs/<queue-id>/.change.staging`; the runner validates and fsyncs the closed six-file result before an
atomic same-parent rename to `jobs/<queue-id>/change`. It then atomically replaces the canonical batch
manifest. A resume:

- revalidates every completed output and never reruns it;
- validates and recovers a fully published directory if interruption happened after the rename but
  before the checkpoint;
- records an `interrupted` failure and removes only the owned partial staging directory if publication
  did not occur; and
- preserves each invocation as `completed` or `interrupted`, with separate recovered/interrupted
  counters.

The per-invocation `--max-jobs` cap defaults to one. Each job also has an immutable subprocess timeout
and total-attempt cap (defaults: 1,800 seconds and three attempts). Command exits, timeouts, output
validation failures, execution errors, and interruptions are distinct failure kinds.

## Offline validation

The validator makes no network request and does not mutate the checkpoint:

```sh
uv run --python 3.12 \
  --with numpy==2.5.1 --with pillow==12.3.0 --with rasterio==1.5.0 \
  python scripts/run_satellite_change_batch.py \
  --queue-dir satellite_review_queues/2026-07-18-global-open-v3 \
  --catalog-batch-dir satellite_review_runs/2026-07-18-global-open-v3-active-001 \
  --output-dir satellite_change_runs/2026-07-18-global-open-v3-active-unreviewed-002 \
  --max-jobs 5 \
  --validate-only
```

`validate_satellite_change_batch(...)` verifies the same lineage in Python. For every completed change
job it requires exactly four PNGs, `change-proposals.geojson`, and `report.json`; verifies PNG structure
and dimensions; reconstructs the selected STAC scene summaries from exact catalog responses; validates
the proposal geometry, counts, and containment in the exact queue AOI (with only a 25 m raster-edge
tolerance); and recomputes all report-bound byte lengths and SHA-256 hashes. Both
the report and every proposal explicitly retain false identity, operator, lifecycle, operating-status,
data-centre-type, IT-capacity, PUE, workload, power, and energy claims plus
`review_required: true`. Algorithm `sentinel-2-l2a-change-v2` uses the projected envelope only for the
bounded COG read. Native windows floor their fractional row and column starts and ceil their absolute
stops, so the far edge cannot discard an AOI pixel center. The red band establishes the exact output
shape, affine transform, and CRS. Bilinear reflectance reprojection reads from the native source band
onto that exact grid only after confirming that the required native covering window plus a one-pixel
interpolation halo fits inside the single asset; this avoids cropped-kernel edge values. Nearest-neighbour
SCL resampling uses its complete covering window and the same red target grid. An AOI whose required
window or interpolation support crosses a single asset grid fails closed rather than accepting a
clipped read. A separately versioned reselection lane may bind full-cover alternate assets already
present in the preserved exact catalog responses. If no qualifying single-asset pair exists, the row
remains unresolved pending a separately versioned mosaic or supplemental-scene capture. The
processor then masks the shared grid back to the
exact WGS84 queue bbox by native-pixel-center inclusion before thresholding and polygonization. Its
`valid_pixel_fraction` is mutually valid pixels inside that exact AOI divided by all native pixel
centers inside the AOI; projected-envelope pixels do not enter the denominator. A grid containing no
pixel center inside the AOI also fails closed. Reports and proposal collections retain the no-inference
schema version `1.1` contract.

Report source metadata pins the Earth Search catalog, approved COG host/path policy, and the official
[Sentinel Data Legal Notice](https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice).
The validator derives an ordered `attribution_notices` array from the exact selected acquisition
datetimes, with one notice per unique year (for example,
`Contains modified Copernicus Sentinel data 2024`).
Archived catalog manifests retain the provider-supplied legal URL they originally recorded, including
the legacy hostname present in existing Earth Search responses, because rewriting that field would
break byte-exact catalog reconstruction. New schema-1.1 change reports use the current official URL
above.

## Imagery-byte reproducibility boundary

The evidence bundle archives and hashes the STAC response documents, selected item IDs, complete STAC
item hashes and asset hrefs, processor/runtime lineage, and every derived output. It does **not**
archive or content-hash the underlying Sentinel COG object bytes or HTTP range responses. A later
bitwise rerun therefore depends on the provider retaining identical bytes at the pinned approved
hrefs. The bundle is an auditable, provider-bound derivation record; it must not be described as a
byte-reproducible archive of the imagery inputs.

Any queue, catalog, configuration, selection, resolved template, processor, runtime, completed output,
path, or symlink drift stops validation and execution before a new change command starts.
