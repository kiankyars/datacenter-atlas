# Google Open Buildings Temporal review lane

This lane proposes bounded annual building-signal changes for analyst review. It does not identify
individual buildings or data centres and does not create lifecycle, construction, operating-status,
capacity, power, or energy observations.

## Official source contract

[Google's Earth Engine catalog](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_Research_open-buildings-temporal_v1)
describes Open Buildings Temporal v1 as annual model rasters for 2016-2023 with three bands:

- `building_fractional_count`: source data for deriving a modelled building-count signal over an
  area;
- `building_height`: modelled height above terrain from 0 to 100 metres, which must be used only in
  conjunction with building presence;
- `building_presence`: uncalibrated model confidence from 0 to 1, usable for relative ranking rather
  than as a probability.

The effective spatial resolution is 4 metres even though the downloadable rasters use a 0.5-metre
storage grid. The lane preserves both facts and never treats storage pixels as independent
half-metre detections. It does not vectorize the output into footprints.

The [official project page](https://sites.research.google/gr/open-buildings/temporal/) reports about
58 million km² of coverage across Africa, South Asia, South-East Asia, Latin America, and the
Caribbean. Coverage is not global, and Google's country list is expressly subject to change. The
model uses stacks of Sentinel-2 imagery around June 30 of each year. Cloud availability,
cross-year image misalignment, fewer usable 2016-2017 frames, temporal instability, and limited
height ground truth in the Global South can all create apparent change. A candidate is therefore a
model-signal proposal, not observed construction.

The dataset offers a choice of CC BY 4.0 or ODbL 1.0. This lane elects CC BY 4.0 and retains Google
Research attribution plus the catalog's link to the Sentinel data legal notice. The static Open
Buildings v3 polygon product is a different dataset and is not copied into this bundle.

## Anonymous, generation-pinned fetch

Google's [official download notebook](https://github.com/google-research/google-research/blob/master/building_detection/open_buildings_temporal_download_region_geotiffs.ipynb)
uses anonymous access to the public `open-buildings-temporal-data` bucket. The source step downloads
the eight annual JSON manifests, verifies each complete object against its GCS generation, size,
and MD5, and records SHA-256 locally. It selects exactly one intersecting COG per year and records
that full object's generation, size, MD5, affine transform, and dimensions. The 351-380 MB COGs are
not copied; extraction uses generation-qualified HTTP range reads for the bounded window.

`rasterio` and `numpy` are optional runtime dependencies. Without them, the source/extraction step
fails with an explicit dependency message; the core atlas package and offline bundle validators
remain dependency-free.

```sh
UV_CACHE_DIR=/private/tmp/open-buildings-uv-cache \
uv run --no-project --with 'rasterio==1.4.3' \
  python3 scripts/fetch_open_buildings_temporal.py \
  --output source_cache/open-buildings-temporal-egy-30.8679-30.8419-source-v2 \
  --generated-at <explicit-timezone-aware-timestamp>
```

## Review extraction and v3 priors

For every year, the extractor verifies the COG profile, reads the same projected AOI window, hashes
the canonical float32 band arrays, and records:

- the sum of the fractional-count signal;
- mean uncalibrated building-presence confidence;
- height statistics only where presence is at least 0.5, with that threshold explicitly labelled
  as a relative screen rather than a probability.

Consecutive years become a review candidate only when fractional-count sum increases by at least
5 and mean presence also increases. These are queue heuristics, not calibrated detection
thresholds. A nearby v3 atlas entity is retained in a separate `atlas-priors.jsonl` file and linked
only as a non-merging review prior; it neither creates nor identifies the change signal.

Open Buildings Temporal is derived from Copernicus Sentinel-2. It therefore shares a sensor
provenance root with the atlas's own Sentinel-2 computer-vision lane and must never count as an
independent corroborating evidence family. The review manifest records this constraint explicitly.

```sh
UV_CACHE_DIR=/private/tmp/open-buildings-uv-cache \
uv run --no-project --with 'rasterio==1.4.3' \
  python3 scripts/extract_open_buildings_temporal.py \
  --input source_cache/open-buildings-temporal-egy-30.8679-30.8419-source-v2 \
  --output source_cache/open-buildings-temporal-egy-30.8679-30.8419-review-v2 \
  --generated-at <explicit-timezone-aware-timestamp>
```

Both outputs have a closed file inventory, canonical manifests, SHA-256 sidecars, directory-atomic
publication, and refusal-on-existing-destination immutability.

After extraction, the derived deltas and candidates can be reconstructed and validated without
network access, Earth Engine credentials, `rasterio`, or `numpy`:

```sh
python3 scripts/validate_open_buildings_temporal.py \
  --source source_cache/open-buildings-temporal-egy-30.8679-30.8419-source-v2 \
  --review source_cache/open-buildings-temporal-egy-30.8679-30.8419-review-v2
```

## Pinned Egypt pilot

The `source-v2` and `review-v2` directories named above are the authoritative checked pilot. Local
`v1` attempts were moved to Trash and must not be cited because their `generated_at` values were
later than the actual run time.

The live pilot covers WGS84 bbox `[30.8658, 30.8399, 30.8699, 30.8439]`, approximately 0.173322
km². Each year produced one `801 × 902` storage-grid window with 722,502 valid storage pixels. The
annual fractional-count signal ranged from 783.695406 to 844.725302; mean presence ranged from
0.289478 to 0.313567. The screen emitted three review intervals: 2017-2018, 2019-2020, and
2022-2023. These are not three buildings and are not evidence that construction occurred.

The one nearby v3 entity is 0.869 m from the AOI centroid and remains explicitly unmerged. Its
proximity explains only why this AOI is useful as a pipeline pilot; candidate selection does not
depend on the prior.

The source manifest SHA-256 is
`3539b0f11ba32120eb8fb054f9d681ebf03995d8719f12b7c828908d357279ac`. The annual-observation
SHA-256 is `b21c2fa5644c8a61fbc57be97ec244a819b2854b81ac98ce2e45984448681744`, the candidate JSONL
SHA-256 is `ec5d8365184d0a1ee7f5122197f59cab4ec908193cdd7964e56cbec6d54b9473`, and the review-manifest
SHA-256 is `b2a49587dcc759794277cdb0d894662328e444f7d7b8ad877c6622bc7dd074c9`.
