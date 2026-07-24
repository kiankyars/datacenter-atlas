# Blind-tile auxiliary integration

The integration core converts candidate-independent, hash-pinned geometry intersections into one deterministic auxiliary row per EPSG:6933 4 km tile. It is implemented and synthetic-fixture tested. The official GHSL cache and current [geometry-complete full-Planet stable OSM v3 derivative](osm_blind_tile_auxiliary_v3.md) are frozen, but the integration has not built a production frame or sample and normalized production geometry streams have not yet been published. The v3 input contains 2,271,693 usable objects and carries 20 unresolved industrial geometries forward explicitly: 18 bounded objects require intersecting tiles to remain incomplete/unknown, while two unlocatable empty relations establish no tile fact.

## Production gates

A production definition fails before the resumable SQLite work database is opened unless all of the following hold:

- the exact seven-file GHSL R2023A cache is present as a non-symlink directory in mode `0555`, every file is mode `0444`, and every byte count and SHA-256 matches the frozen contract;
- the stable OSM derivative has the pinned directory name, passes its own frozen-bundle validator, and its manifest SHA-256 equals the definition pin;
- the Natural Earth artifact and all four normalized inputs match their byte counts and SHA-256 values;
- the integration module and CLI bytes equal the checkpoints in the canonical definition;
- all input paths are relative, stay within the definition's project root, contain no construction master/map, candidate fusion, satellite queue, OSM structural shortlist, or release reference, and have no symlink in any lexical path component before resolution. A symlink is rejected even when it resolves to the exact same hash-valid target.

The four normalized streams are a strict interface, not a provenance shortcut. Their source roles are literal in the definition contract: land denominators may use only Natural Earth; BUILT and SMOD fragments may use only their respective frozen GHSL layer plus Natural Earth; and OSM observations may use only the frozen stable derivative plus Natural Earth. Candidate-derived sources are false for every role.

Producer bytes and independent source-to-stream validation do not yet exist. The implementation therefore rejects every non-fixture definition with a hard blocker even after its frozen raw-source gates pass. A production build cannot be enabled by merely writing a definition that asserts lineage. Enabling it requires a reviewed, byte-pinned producer and independent validation that recomputes the normalized streams from the permitted raw artifacts; until then no production auxiliary, frame, or sample result can be emitted.

## Canonical streaming interface

All streams are canonical JSONL, ordered in the definition as `tiles`, `built_cells`, `smod_cells`, and `osm_tiles`. Geometry is measured in EPSG:6933 and every area is an integer number of square millimetres.

- `tiles`: `tile_id`, positive non-Antarctic `land_area_mm2`.
- `built_cells`: source-cell ID, integer `built_surface_m2` or `null`, exact source-cell land area, and sorted positive tile-land fragments that close exactly to that area.
- `smod_cells`: source-cell ID, one of `10, 11, 12, 13, 21, 22, 23, 30` or `null`, exact source-cell land area, and the same exact fragment contract.
- `osm_tiles`: tile ID, complete-processing flag, stable-industrial union intersection area, and a paired minimum grid distance/maximum voltage observation or two nulls.

The builder reads bounded batches and commits the input byte offset, row count, source checkpoint, and aggregates in SQLite. A resumed run rejects a different definition or changed input, but the mutable resume database is never accepted as evidence for publication. Before publication, and on every validation supplied with the external definition, all four hash-bound streams are replayed into a separate fresh SQLite database. Its canonical output is compared with the proposed bundle row-for-row in lockstep and its canonical coverage document must match byte-for-byte. A one-unit mutation of a partially built SMOD aggregate therefore prevents publication and leaves no output bundle.

Output, work-database, deterministic sibling-temporary, SQLite sidecar, definition, and input paths are checked for equality and ancestor/descendant overlap before SQLite is opened. A pre-existing sibling temporary path also fails at that point. Final rows are streamed in tile-ID order into a new temporary bundle, fully hashed and semantically validated. Every written file is flushed and `fsync`ed; the temporary directory and parent are `fsync`ed before the sibling rename, and the parent is `fsync`ed again afterward. Frozen builds apply `0555/0444` before that durable atomic rename. A fixed clock produces byte-identical output regardless of batch size or interruption point.

## Frozen semantics

GHS-BUILT-S is extensive. Each valid integer-square-metre source value is converted to integer square millimetres and allocated among its tile-land fragments with floor division followed by deterministic largest remainder, ordered by remainder then tile ID. Allocation closes exactly for every source cell and globally. Bilinear interpolation is forbidden. The signal is true at or above `1/200` of tile land, false only with full valid tile-land coverage below threshold, and otherwise unknown. A known lower bound can therefore be true despite missing or nodata coverage.

GHS-SMOD remains categorical. Codes `21, 22, 23, 30` are urban, and any positive urban-coded intersection makes the signal true. A negative requires complete valid non-urban tile-land coverage; nodata or missing coverage otherwise remains unknown. Resampling is not part of the intersection calculation; nearest-neighbour is the only permitted implementation aid if it reproduces the exact categorical result.

Stable OSM industrial is true at a union intersection of at least 10,000 m². Grid is true for a parsed feature of at least 110 kV at a distance no greater than 5 km. Below-threshold results are false only when OSM processing is complete; otherwise they remain unknown. Unknowns count as false only when assigning the recorded lower-bound stratum and remain explicitly listed on the row.

Bundle validation recomputes every BUILT, SMOD, urban, industrial, grid, unknown-field, and lower-bound-stratum value from the stored primitive areas. External validation additionally performs the independent four-stream replay, so redistributing primitive area between output rows and rewriting every affected manifest hash still fails exact comparison.

## Current verification

The synthetic suite covers exact threshold boundaries, one-square-millimetre SMOD urban overlap, nodata and missing tri-state behavior, absent and incomplete OSM rows, largest-remainder ties, per-source and global conservation, byte-identical resumability, partial-database SMOD tampering, source-primitive redistribution after manifest rehashing, identical-target symlink aliases, every output/work/temporary overlap class, pre-existing sibling temporary paths, publication `fsync` ordering, frozen inventory, forbidden candidate paths, missing production OSM lineage, and semantic tampering after manifest rehashing.

```bash
python -m unittest tests.test_blind_tile_auxiliary_integration
```

No network request and no Planet-scale or global-raster build is made by that test.
