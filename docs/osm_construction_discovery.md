# OSM structural construction discovery

This lane scans one hash-verified, dated OpenStreetMap Planet for explicitly tagged structural
construction and proposal objects. It is a blind-discovery review queue, not a data-centre census
and not an importer into the atlas database.

## Bounded filter

Filter contract `osm-structural-construction-v1` is a fixed, SHA-256-bound ordered list. Its primary
surface covers:

- `building`, `landuse`, `site`, `man_made`, `industrial`, or `power` exactly tagged
  `construction` or `proposed`;
- the corresponding `construction:*` and `proposed:*` structural keys;
- `construction=` or `proposed=` with a finite allowlist of building, commercial, factory,
  industrial, logistics, manufacture/manufacturing, plant, storage, warehouse, or works values;
- `man_made=foundation`.

Only `power=plant` and `power=substation` are added as context objects. The filter does not use
generic `construction=*`/`proposed=*`, names, descriptions, roads, rail, waterways, or arbitrary
text. Osmium expressions are ORed and case-sensitive. `tags-filter` runs without `-R` or
`--omit-referenced`, and `osmium check-refs -r` must pass before the filtered PBF and manifest are
published.

Inspect the exact command without scanning the Planet:

```sh
python3 scripts/extract_osm_planet_construction.py \
  --source source_cache/osm-planet-260713/planet-260713.osm.pbf \
  --dry-run
```

Run against the verified 2026-07-13 Planet:

```sh
python3 scripts/extract_osm_planet_construction.py \
  --source source_cache/osm-planet-260713/planet-260713.osm.pbf \
  --fetch-manifest source_cache/osm-planet-260713/fetch-manifest.json
```

The source is checked against the pinned official byte count and MD5 before extraction; the
manifest additionally records its SHA-256 and fetch-manifest hash. Existing output is reused only
after its complete contract and bytes revalidate. Temporary files are exclusive and cleaned on
failure.

## Lossless matched layer and review prior

The materializer converts the reference-complete PBF to temporary OSM XML. Every primary match is
emitted exactly once with its typed OSM ID, canonical URL, original tags, preserved version metadata,
node/member references, and available geometry. Relation polygons use the existing role-aware ring
assembler; missing references stop publication. The XML is an internal bridge and is removed before
the atomic directory rename.

Polygon footprints use a documented local-equirectangular shoelace calculation with inner rings
subtracted. Review points are transparent and deterministic:

- footprint at least 10k/20k/50k/100k m²: 1/2/3/4 points;
- explicit industrial token in a structural source tag: 2 points;
- explicit electrical token in a structural source tag: 2 points;
- mapped power plant/substation centre within 2 km/5 km: 2/1 points.

An object enters the shortlist only with a polygon footprint of at least 10,000 m² and at least
three points. Area and centre-distance calculations are approximations for prioritization, not
facility, power, or energy estimates.

Objects explicitly tagged as power plants, substations, generators, or transformers—including
`construction:power` / `proposed:power` assets—remain in the raw and context layers but are excluded
from the shortlist in their own counted stage. This prevents a mapped power project from treating
itself as zero-distance electrical context. The exclusion is based only on the source tag.

The materializer is bound to the canonical exact OSM materialization from the identical Planet
SHA-256. Equality of `(OSM object type, OSM ID)` is the only automatic identity link. Linked exact
objects remain in the full matched layer, are written to `known-data-centre-links.json`, and are
excluded from the shortlist. If a primary match carries a canonical exact tag but is absent from the
exact layer, the build fails closed.

```sh
python3 scripts/build_osm_construction_candidates.py
```

The immutable bundle contains ordered compressed JSONL for all matched source objects, a
reference-complete primary PBF, compressed context-centre JSONL, linked-exclusion JSON, ordered
GeoJSON and CSV shortlists, attribution, README, and a manifest hashing every payload and both
upstream layers. The JSONL preserves typed identity, tags, version metadata, and node/member IDs; the
PBF retains the coordinate/member objects needed to resolve those references. A valid existing
bundle is reused; a tampered or incomplete bundle is rejected. The whole directory is built beside
its destination and published by a same-filesystem atomic rename.

The checked 2026-07-18 v3 build from the 2026-07-13 Planet contains 1,446,595 raw primary matches,
1,429,198 polygon geometries, and 102,451 shortlisted polygons. It records 126 exact typed links to
the canonical data-centre layer, of which 125 have polygon geometry and are excluded at the known-ID
stage. The manifest separately reconciles retained references, context objects, missing polygon
geometry, explicit power-asset exclusions, footprint exclusions, score exclusions, and shortlisted
objects.

## Interpretation boundary

A shortlist row means only: “this mapped OSM object has an explicit source construction/proposal
tag and satisfies the published review prior.” The lane never infers data-centre identity, lifecycle
state, capacity, workload, operator, facility type, electricity demand, or energy consumption.
Manual review and independent evidence are required before any candidate can become a data-centre
claim.

All distributed OpenStreetMap-derived data must retain © OpenStreetMap contributors attribution and
comply with ODbL 1.0.
