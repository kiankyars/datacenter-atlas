# Geometry-complete full-Planet OSM blind-tile auxiliary v2

> **Rejected and superseded evidence.** The frozen v2 directory is retained
> byte-for-byte for audit, but it is not a valid/current auxiliary and must not
> be consumed. Its explicit-`outer` relation gate rejected 95 industrial
> relations that pinned libosmium 2.23.1 successfully exports as polygons. Use
> the separately versioned v3 bundle and contract instead; never overwrite the
> retained v2 directory.

Version 2 is a candidate-independent industrial/grid context derivative of the pinned `planet-260713.osm.pbf` snapshot. It does not consume Atlas entities, candidate fusion, construction outputs, satellite queues, structural shortlists, or the v1 derivative. The protected v1 selector, CLI, and frozen release remain unchanged.

This is an auxiliary context layer, not a data-centre detector, site list, construction claim, or negative finding.

## Why v2 exists

An independent polygon reconciliation of v1 found 1,430,205 selected industrial objects but only 1,430,185 matching source polygons. The exact 20-object gap comprised two `area=no` ways, empty/no-outer/relation-only multipolygons, self-crossing ways, and relations whose rings could not assemble. Osmium emitted only 14 generic geometry errors, so stderr counts cannot safely identify the missing source objects.

V2 therefore treats polygon identity reconciliation—not `check-refs` alone—as a required industrial-selection gate.

## Deterministic pipeline

The full-Planet broad scan and tag rules remain candidate-independent. V2 then:

1. Rejects explicit `area=no` ways and relations with no members, no outer member, or no outer way member before accepting their industrial signal. A separately qualified grid signal is retained.
2. Materializes every candidate and all recursive references from the same pinned Planet.
3. Builds an industrial-only provisional PBF with non-selected reference tags removed.
4. Streams a complete osmium GeoJSON-sequence polygon export with unique area IDs, decodes each area ID back to its source way/relation, and compares the exact expected and exported identity sets. Generic osmium diagnostics are recorded but never assigned to individual objects.
5. Writes every structural rejection and every missing exported identity to canonical `unresolved-geometry-ledger.jsonl` before removing its industrial signal from the usable inventory.
6. Rebuilds the final PBF from usable industrial IDs plus every qualified grid ID, runs `osmium check-refs --check-relations`, and requires an exact stop-on-error polygon export bijection for the ledger-defined industrial subset.

Grid points, lines, and polygons remain eligible according to the existing voltage rules. If an object has both signals and its industrial geometry is unresolved, its grid signal and source geometry remain in the PBF with `geometry_status=grid_preserved_industrial_unresolved`; downstream consumers must use `selection-ledger.jsonl`, not raw tag presence, to interpret selected signals.

## Unresolved geometry and downstream coverage

No geometry is repaired or invented.

For each unresolved object, v2 recursively follows its referenced nodes and records only the conservative WGS84 node envelope when coordinates exist. Every downstream tile whose closed footprint intersects that envelope must mark industrial coverage `incomplete_unknown`; the object may not be treated as false in those tiles.

If an empty or otherwise unlocalizable object has no referenced-node coordinates, its bounds are `null`, `geometry_invented` is `false`, and the record explicitly establishes no locatable tile fact. This is an object-local exclusion, not a reason to fabricate a location or mark global coverage complete.

## Integrity and publication

The manifest has an exact schema and pins:

- the full Planet size, MD5, SHA-256, snapshot date, URL, and adjacent acquisition manifest;
- Python and platform runtime values;
- osmium/libosmium versions plus the executable path, bytes, and SHA-256;
- the protected v1 selection dependency, v2 module, and v2 CLI bytes;
- exact normalized command contracts, filter semantics, counts, fileinfo, output hashes, rights, and downstream unresolved rules.

Extraction rechecks processor/runtime/osmium lineage during the run and, by default, rehashes the complete Planet after long work. It builds in a sibling staging directory, fsyncs all artifacts, removes intermediates, freezes files to `0444` and the directory to `0555`, performs full offline semantic validation, then atomically renames the directory and fsyncs its parent. Invalid staging is never published.

## Commands

Inspect the contract without scanning imagery, Atlas, or the Planet:

```bash
python3 scripts/extract_osm_blind_tile_auxiliary_v2.py --dry-run
```

Run the pinned full-Planet extraction once to a new path:

```bash
python3 scripts/extract_osm_blind_tile_auxiliary_v2.py
```

Validate the frozen bundle and rerun check-refs plus the exact stop-on-error industrial polygon export. The first command avoids rereading the 93.9 GB Planet; the second also recomputes its hashes:

```bash
python3 scripts/extract_osm_blind_tile_auxiliary_v2.py \
  --verify-only --skip-deep-source-hash
python3 scripts/extract_osm_blind_tile_auxiliary_v2.py --verify-only
```

Run the fixture regressions:

```bash
PYTHONDONTWRITEBYTECODE=1 \
  python3 -m unittest tests.test_osm_blind_tile_auxiliary_v2
```

## Limitations

OSM tagging and geometry remain incomplete and snapshot-bound. A conservative referenced-node envelope is not a polygon and must only propagate coverage uncertainty. Naive WGS84 envelopes can be broad near the antimeridian. Raw industrial tags can remain on a mixed object retained solely for its qualified grid signal, so selection semantics come from the ledger. V2 neither repairs invalid OSM geometry nor turns unresolved absence into zero area, a false tile, or an Atlas fact.
