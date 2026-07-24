# Bounded Overture building discovery

This lane searches for large, industrial-shaped building footprints that are absent from or merely
near the current atlas. It is a **review queue**, not a data-centre classifier. A large rectangular
building may be a warehouse, factory, airport terminal, cold store, school, retail building, or many
other things. The output makes no identity, lifecycle, operating-status, power, or energy claim and
is never imported automatically.

## Pinned Memphis pilot

The checked bundle uses the official Overture Maps `2026-06-17.0` release (schema `v1.17.0`),
`buildings/building` theme/type, and `overturemaps` CLI `1.0.1`. Its bbox is exactly
`-90.10,34.95,-89.95,35.10`. The official release path is:

```text
s3://overturemaps-us-west-2/release/2026-06-17.0/theme=buildings/type=building/*
```

The CLI state did not retain the exact argv used for the completed fetch, so the manifest says so
and records this pinned reproduction command rather than claiming it is the captured invocation:

```sh
UV_CACHE_DIR=/private/tmp/datacenter-atlas-uv-cache \
uvx --from overturemaps==1.0.1 overturemaps download \
  --bbox=-90.1,34.95,-89.95,35.1 \
  -f geojsonseq \
  --type=building \
  --release=2026-06-17.0 \
  --output=buildings.geojsonseq
```

The source release is GeoParquet; the official CLI writes the bounded result as GeoJSONSeq. The
materializer accepts ordinary newline-delimited GeoJSON and RFC 8142 record-separator-prefixed
GeoJSONSeq using only the Python standard library. It copies the source bytes exactly into the
bundle. It validates every GERS UUID, complete Polygon/MultiPolygon geometry including holes, source
record, source license, timestamp, record count, and bbox intersection. A `0.00001°` validation
tolerance is explicit because four CLI-returned Memphis polygons fall entirely less than one metre
outside a bbox edge due to coordinate precision; anything beyond that tolerance fails closed.

Build the checked pilot from the completed local fetch:

```sh
python3 scripts/build_overture_building_candidates.py \
  --input /private/tmp/overture-memphis-20260617.geojsonseq \
  --fetch-state /private/tmp/overture-memphis-20260617.geojsonseq.state \
  --atlas releases/2026-07-18-global-open-v3/atlas.geojson \
  --output source_cache/overture-2026-06-17.0-memphis \
  --generated-at 2026-07-18T20:00:00Z
```

Publication is atomic: all files are written and fsynced in a temporary sibling directory, the
complete bundle is reconstructed and validated, and only then is the directory renamed into place.
Existing output is never overwritten. `manifest.sha256` binds the canonical manifest, and the
manifest binds the exact raw fetch, CLI state, compact v3 atlas reference inventory, candidate
GeoJSONSeq, and candidate CSV by byte count and SHA-256.

## Transparent measurements and shortlist

For each full footprint, longitude/latitude vertices are projected locally with the mean Earth
radius and an equirectangular approximation. Shoelace areas are computed for every polygon outer
ring minus every hole; MultiPolygon areas and centroids are area-weighted. Rectangularity is the
footprint area divided by its local axis-aligned bounding-box area. Both are explicitly approximate
screening measurements, not surveyed floor area or usable data-hall area.

A feature is shortlisted when either:

- approximate footprint area is at least 25,000 m²; or
- area is at least 10,000 m² and `class` or `subtype` is explicitly one of `factory`, `hangar`,
  `industrial`, `manufacturing`, or `warehouse`.

Rectangularity is reported but is not a hidden selection gate. Every candidate retains the original
geometry, GERS ID, complete Overture properties, every `sources[]` item and license, earliest/latest
source update time, exact selection reasons, and the fixed review safeguards.

## Non-merging atlas cross-reference

The bundle hash-binds the entire `2026-07-18-global-open-v3` atlas and also stores a compact,
self-validating inventory of all coordinate-bearing atlas entities. Overture OpenStreetMap
`record_id` values are compared only with explicit atlas OSM stable keys and OpenStreetMap URLs.
Exact matches are listed; no entity is merged or modified. OSM-derived but source-scoped identifiers
from other adapters are not guessed into the OSM namespace.

For all other candidates, Haversine distance is measured from the derived footprint centroid to the
nearest v3 atlas coordinate. Labels distinguish exact upstream identity, within 100 m, within 500 m,
within 2 km, and no v3 atlas coordinate within 2 km. “Novel” therefore means only novel relative to
this particular v3 atlas and threshold—it is not evidence that the building is new, unknown to all
sources, under construction, or a data centre.

The Memphis pilot contains 62,456 source footprints and 96 shortlist rows: two exact upstream OSM
matches, three non-exact candidates within 2 km of a v3 coordinate, and 91 with no v3 atlas
coordinate within 2 km. This is one bounded Memphis-area pilot. It is not global coverage, a recall
estimate, or a completeness claim.

## Rights and attribution

The Overture buildings theme is ODbL. The bundle preserves the feature-level upstream license
strings and inventories OpenStreetMap, Microsoft ML Buildings, and Esri Community Maps separately.
Retain `© OpenStreetMap contributors, Overture Maps Foundation` and consult Overture's
[buildings guide](https://docs.overturemaps.org/guides/buildings/),
[release notes](https://docs.overturemaps.org/blog/2026/06/17/release-notes/), and
[attribution guidance](https://docs.overturemaps.org/attribution/) before redistribution.
