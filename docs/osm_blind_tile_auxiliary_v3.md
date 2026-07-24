# Geometry-complete full-Planet OSM blind-tile auxiliary v3

Version 3 is a candidate-independent industrial/grid context derivative of the pinned `planet-260713.osm.pbf` snapshot. It does not consume Atlas entities, candidate fusion, construction outputs, satellite queues, structural shortlists, or either frozen derivative. The protected v1 release and rejected v2 evidence remain unchanged.

This is an auxiliary context layer, not a data-centre detector, site list, construction claim, or negative finding.

## Why v3 exists

An independent polygon reconciliation of v1 found 1,430,205 selected industrial objects but only 1,430,185 matching source polygons. The exact 20-object gap comprised two `area=no` ways, empty/relation-only multipolygons, self-crossing ways, and relations whose rings could not assemble. Osmium emitted only 14 generic geometry errors, so stderr counts cannot safely identify the missing source objects.

V3 therefore treats polygon identity reconciliation—not `check-refs` alone—as a required industrial-selection gate.

The first attempted implementation was published as frozen v2 evidence and then rejected. It treated an explicit `outer` role as a structural requirement and pre-rejected 97 relations. An independent extraction of those 97 objects from frozen v1, followed by the pinned libosmium polygon exporter, proved:

- 30 relations had at least one blank-role direct way member;
- 66 were inner-only and one used another role;
- libosmium emitted exactly 95 source-reconciled relation polygons: all 30 blank-role, 64 inner-only, and the other-role relation;
- only `r18767522` and `r20451029` failed geometry assembly.

The frozen v2 bundle is preserved byte-for-byte under `source_cache/osm-blind-tile-auxiliary-260713-v2`, but it is rejected and must not be consumed. V3 is a new processor, manifest schema, output path, and release.

## Deterministic pipeline

The full-Planet broad scan and tag rules remain candidate-independent. V3 then:

1. Rejects explicit `area=no` ways, empty relations, and relations with no direct way member before accepting their industrial signal. Blank, `inner`, `outer`, and other direct-way roles all proceed to the pinned polygon exporter because roles alone do not determine assembly success. A separately qualified grid signal is retained.
2. Materializes every candidate and all recursive references from the same pinned Planet.
3. Builds an industrial-only provisional PBF with non-selected reference tags removed.
4. Streams a complete osmium GeoJSON-sequence polygon export with unique area IDs, decodes each area ID back to its source way/relation, and compares the exact expected and exported identity sets. Generic osmium diagnostics are recorded but never assigned to individual objects.
5. Writes every structural rejection and every missing exported identity to canonical `unresolved-geometry-ledger.jsonl` before removing its industrial signal from the usable inventory.
6. Rebuilds the final PBF from usable industrial IDs plus every qualified grid ID, runs `osmium check-refs --check-relations`, and requires an exact stop-on-error polygon export bijection for the ledger-defined industrial subset.

Grid points, lines, and polygons remain eligible according to the existing voltage rules. If an object has both signals and its industrial geometry is unresolved, its grid signal and source geometry remain in the PBF with `geometry_status=grid_preserved_industrial_unresolved`; downstream consumers must use `selection-ledger.jsonl`, not raw tag presence, to interpret selected signals.

## Unresolved geometry and downstream coverage

No geometry is repaired or invented.

For each unresolved object, v3 recursively follows its referenced nodes and records only the conservative WGS84 node envelope when coordinates exist. Every downstream tile whose closed footprint intersects that envelope must mark industrial coverage `incomplete_unknown`; the object may not be treated as false in those tiles.

If an empty or otherwise unlocalizable object has no referenced-node coordinates, its bounds are `null`, `geometry_invented` is `false`, and the record explicitly establishes no locatable tile fact. This is an object-local exclusion, not a reason to fabricate a location or mark global coverage complete.

## Frozen production result

The one approved full-Planet run completed from `2026-07-19T11:33:33Z` through `2026-07-19T12:11:33Z` and published `source_cache/osm-blind-tile-auxiliary-260713-v3` only after prepublication validation.

- The broad scan examined 3,624,326 tagged objects and selected 2,271,713 stable candidates: 1,430,205 industrial and 844,559 qualified grid objects, with 3,051 in both sets.
- Structural preselection rejected six industrial signals: two explicit `area=no` ways, two empty relations, and two relations with no direct way member.
- The initial complete polygon export expected 1,430,199 industrial objects, emitted 1,430,185 exact source identities, and left 14 exporter-resolved failures. The diagnostics contained 14 lines, but object identity comes only from expected-versus-emitted reconciliation.
- The final usable inventory contains 2,271,693 objects: 637 nodes, 2,205,978 ways, and 65,078 relations; 1,430,185 have industrial signal, 844,559 have grid signal, and 3,051 have both.
- The unresolved ledger contains exactly the same 20 source identities found by the independent v1 audit; its ordered identity digest is `d9696975bfa07d089accf9d4c18248fe3920c49282c7de40b2217635c7b5daa3`. Eighteen have conservative bounds and require intersecting-tile `incomplete_unknown`; the two empty relations have null bounds and establish no tile fact.
- Final `check-refs --check-relations` reported zero missing node, way, or relation references. The final stop-on-error industrial export reproduced all 1,430,185 expected identities with no diagnostics.
- The final directory is `0555`; all six artifacts are `0444`. Independent `--verify-only --skip-deep-source-hash` validation passed after publication, and the combined v1/v2/v3 fixture suite passed 36 tests.

Pinned v3 artifact checkpoints are:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `stable-industrial-grid-geometry-complete.osm.pbf` | 400,035,749 | `f1d1d2446a77bf1973d7c59e23392a38c6eb5ffcfa294e363a472332b08b0e2c` |
| `selected-feature-ids.txt` | 25,674,723 | `c91face594a9378d8a35a3713889dd201f95833bd7aac1925b80d05351e4ae3f` |
| `selection-ledger.jsonl` | 385,424,340 | `709d9bda649f55a1d1f079004b13b0c64f7f0ee4fee6d4d1936066c972475bab` |
| `unresolved-geometry-ledger.jsonl` | 12,210 | `04883a773607146037ef27d60fa4b4d4aa570b034364583ec09fca52a69dc323` |
| `extract-manifest.json` | 15,680 | `f4b541170aa90045c36332251f65b941e92cf81ddb5dc9f771ada6790eb2191b` |
| `manifest.sha256` | 88 | `63cd7202f9541afe5d03949afb070f37a2138ff296007aeb910cc978b98d0e22` |

The rejected v2 directory was not overwritten or deleted. Rechecking all six of its artifact hashes produced inventory digest `795769e0a55b23e8aff07be42390e00ab79f85c5f0f3d669519c7a534119dde0`; the corresponding v3 inventory digest is `99e6e95f00562982e7196bf4234ac449d3caf4f0a2cc8d1fac25a07693de23e7`.

## Integrity and publication

The manifest has an exact schema and pins:

- the full Planet size, MD5, SHA-256, snapshot date, URL, and adjacent acquisition manifest;
- Python and platform runtime values;
- osmium/libosmium versions plus the executable path, bytes, and SHA-256;
- the protected v1 selection dependency, v3 module, and v3 CLI bytes;
- exact normalized command contracts, filter semantics, counts, fileinfo, output hashes, rights, and downstream unresolved rules.

Extraction rechecks processor/runtime/osmium lineage during the run and, by default, rehashes the complete Planet after long work. It builds in a sibling staging directory, fsyncs all artifacts, removes intermediates, freezes files to `0444` and the directory to `0555`, performs full offline semantic validation, then atomically renames the directory and fsyncs its parent. Invalid staging is never published.

## Commands

Inspect the contract without scanning imagery, Atlas, or the Planet:

```bash
python3 scripts/extract_osm_blind_tile_auxiliary_v3.py --dry-run
```

Run the pinned full-Planet extraction once to a new path:

```bash
python3 scripts/extract_osm_blind_tile_auxiliary_v3.py
```

Validate the frozen bundle and rerun check-refs plus the exact stop-on-error industrial polygon export. The first command avoids rereading the 93.9 GB Planet; the second also recomputes its hashes:

```bash
python3 scripts/extract_osm_blind_tile_auxiliary_v3.py \
  --verify-only --skip-deep-source-hash
python3 scripts/extract_osm_blind_tile_auxiliary_v3.py --verify-only
```

Run the fixture regressions:

```bash
PYTHONDONTWRITEBYTECODE=1 \
  python3 -m unittest tests.test_osm_blind_tile_auxiliary_v3
```

## Limitations

OSM tagging and geometry remain incomplete and snapshot-bound. A conservative referenced-node envelope is not a polygon and must only propagate coverage uncertainty. Naive WGS84 envelopes can be broad near the antimeridian. Raw industrial tags can remain on a mixed object retained solely for its qualified grid signal, so selection semantics come from the ledger. V3 neither repairs invalid OSM geometry nor turns unresolved absence into zero area, a false tile, or an Atlas fact.
