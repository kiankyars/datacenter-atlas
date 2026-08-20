# Colossus 2 Sentinel-2 change pilot

This is a bounded, reproducible imagery-evidence pilot for the known Epoch AI campus entity
`7584d004-d8d5-50e7-9071-3dd6adca2f30`. It is not a data-centre detector and makes no claim about
power or operating status.

The catalog manifest records two exact Earth Search STAC responses and their SHA-256 hashes. The
selected pair is Sentinel-2 L2A tile `16SBD` on 2024-06-13 and 2026-06-23. Both scenes were read as
cloud-optimized GeoTIFF windows over the explicit WGS84 AOI; STAC band scales and offsets were
applied, SCL cloud/shadow/snow pixels were masked, and the same 10 m grid was used for both dates.

The deterministic detector marks large spectral transitions for analyst review. In this pilot,
96.7% of pixels were mutually valid and nine connected proposal components above 5,000 m² totaled
341,300 m². Those figures describe changed optical pixels, not new building floor area.

Files:

- `catalog/manifest.json`: queries, rights, normalized results, selected IDs, and raw-response hashes.
- `catalog/*-response.json`: exact saved STAC responses.
- `change/before.png`, `after.png`, and `change-overlay.png`: inspectable images.
- `change/comparison.png`: baseline, current, and proposal overlay from left to right.
- `change/change-proposals.geojson`: review geometries; every feature explicitly has
  `identity_claim=false`.
- `change/report.json`: algorithm, band URLs, thresholds, metrics, limitations, and output hashes.

Reproduce the catalog request with `scripts/catalog_satellite.py`, then run
`scripts/sentinel_change.py` under the optional `numpy`, `pillow`, and `rasterio` runtime described
by that script's error message.
