# Within-release entity resolution

The within-release lane is the redistribution-safe, deterministic replacement for treating a
large-radius search as a deduplication result. It reads immutable `atlas.geojson` files, never
modifies a child release, and emits manual-review candidates independently inside each release.
It does not compare records across separately licensed children, accept a relationship, merge an
entity, or calculate unique physical sites.

## Candidate classes

Only three classes are published:

- `shared_source_identity` requires an exact typed source token. Direct OSM stable keys preserve
  node/way/relation identity. PNNL/IM3 rows preserve their versioned layer/source ID and, because
  that dataset is OSM-derived, its zero-padded numeric source ID is normalized to the applicable
  OSM node/way candidate (campus polygons may originate from a way or relation). Epoch
  `source_record_id` and Wikidata QID identities are scoped to their source families. Generic
  dataset URLs and DOIs never count as identities.
- `tight_same_site` compares different source families, equal entity kinds, and points at most
  250 m apart. It requires score at least 0.62 and name, usable street/postcode address, or
  owner/operator similarity at least 0.82.
- `part_of` compares different source families across the campus/facility/building/project
  hierarchy at most 750 m apart. It requires score at least 0.55 plus containment or a published
  high-similarity name/address/operator gate. Suggested parent and child IDs are review hints.

The score is `0.35 distance + 0.30 name + 0.15 address + 0.12 owner/operator + 0.08 geometry`.
Distance decays to zero at 1 km. Exact typed identity candidates are floored at 0.99, but remain
advisory. Empty, country-only, or state-only addresses do not create address similarity. There are
no `nearby_only` rows.

## Provenance and structural records

Every candidate retains release ID, entity kind, stable key, evidence ID, source family, source
root, and the exact signals used. PNNL/IM3 and direct OSM both use the `openstreetmap` provenance
root, so their links are marked `source_independent=false`; spatial agreement between them is not
independent corroboration. Same-organization page and press-release families are also collapsed to
one root where applicable.

Source-generated facility containers and development-project companions can legitimately share a
typed source object with a building or facility. Those rows are retained as structural review
candidates and explicitly set `source_generated_structure=true`; they are not duplicate-site
claims. Any entire release whose manifest declares `review_only=true` is excluded before its
GeoJSON is scanned. This also prevents fuzzy or structural-polygon discovery layers from entering
the lane merely because they are nearby.

## Immutable definitions and bundles

Definitions under `sources/within-release-resolution-*.json` pin every child manifest, the review
scope expectation, thresholds, and (when present) the public federation manifest. Relative paths
make the definition portable while its raw bytes are SHA-256 checkpointed in the output.

Each closed output directory contains:

- `resolution-candidates.json` and a byte-equivalent canonical CSV;
- `summary.json`, including excluded review-only counts and candidate/root breakdowns;
- `ATTRIBUTION.txt` with each input's disposition;
- the lane's generated `README.md`;
- `manifest.json` and `manifest.sha256`, binding the definition, federation, child manifests,
  child GeoJSON, thresholds, policy, counts, and every payload byte.

Publication uses a sibling staging directory, exclusive file creation, file and directory fsync,
offline semantic validation, complete input revalidation, and atomic rename. A valid existing
directory is accepted only if every byte is identical.

```sh
python3 scripts/build_within_release_resolution.py \
  --definition sources/within-release-resolution-2026-07-18-global-open-v3-v1.json \
  --output-dir within_release_resolution/2026-07-18-global-open-v3-v1

python3 scripts/build_within_release_resolution.py \
  --definition sources/within-release-resolution-2026-07-18-public-open-v1.json \
  --output-dir within_release_resolution/2026-07-18-public-open-v1 \
  --validate-only --verify-inputs
```

The validator is network-free. With `--verify-inputs`, it revalidates every release and federation
checkpoint, rebuilds the candidate set, and requires a byte-identical bundle.

## Checked 2026-07-18 bundles

`2026-07-18-global-open-v3-v1` and `2026-07-18-public-open-v1` each contain 8,586 links:
5,936 typed shared-source identities, 588 tight same-site candidates, and 2,062 part-of
candidates. Of those links, 8,552 share an upstream provenance root and 34 join independent roots;
5,748 explicitly involve a generated structural companion. The public bundle processes 9,375
non-review records across its open-seed and global children and excludes all 6,130 fuzzy-review
records. The open seed produces no qualifying within-child pair, so the two candidate payloads are
byte-identical; this does not authorize comparison across children.

The global bundle manifest SHA-256 is
`46c3b04ea27db6a191eb13e0aa0521168a074d02a275bb3a398fdb9565a3934f`; the public bundle
manifest SHA-256 is
`41938ae7bcd83c52899afe08d546a94b38c5c15ae3dadcfaaaead3f4b6986ae6`. Both candidate JSON
payloads hash to `76c684c45d2c3a9bf394b226054647b46c468d766a9657f3f1e429d572771e03`.
