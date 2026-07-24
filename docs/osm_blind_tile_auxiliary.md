# Full-Planet OSM blind-tile auxiliary

The frozen derivative at `source_cache/osm-blind-tile-auxiliary-260713-v1` is a candidate-independent industrial/grid context layer for the blind 4 km frame. It is not a data-centre detector, a facility list, or construction evidence, and it has not built a production frame or sample.

## Pinned source and extraction

The only source is the official `planet-260713.osm.pbf` snapshot plus its adjacent acquisition manifest. The Planet file is 93,874,282,582 bytes, has locally recomputed SHA-256 `14774547661414e1b5df31558aa402d2e489b97e16966f319b0e6e059bd31eb4`, and matches the publisher's MD5 `f6b3e7b85e291713f1413442017e24a4`. Its recorded OSM maximum timestamp is `2026-07-12T23:59:57Z`.

The broad streaming scan reads area-capable `landuse=industrial` or `industrial=*` objects and nodes, ways, or relations tagged `power=substation`, `power=line`, or `power=cable`. It then:

- keeps industrial objects only when area-capable;
- keeps grid objects only when a strict parser finds at least 110,000 V in `voltage`, `voltage:primary`, `voltage:secondary`, or `voltage:tertiary`;
- excludes explicit proposed, construction, inactive, disused, abandoned, demolished, destroyed, razed, removed, or equivalent lifecycle tags;
- excludes structured data-centre identity keys and a pinned multilingual value lexicon;
- records unlisted languages and synonyms as a residual leakage blocker rather than claiming a perfect blind exclusion; and
- recovers only the selected objects' recursive references from the same Planet snapshot, strips reference-only tags, and requires `osmium check-refs --check-relations` to pass.

No construction master/map, candidate fusion, satellite queue, structural shortlist, or Atlas release is an input. Broad matches, selected objects, and tile signals are not sites and must never be promoted automatically.

## Frozen result

The selector scanned 3,624,326 broad objects. It retained 2,271,713 objects: 637 nodes, 2,205,982 ways, and 65,094 relations. The selected union comprises 1,430,205 industrial objects, 844,559 grid objects, and 3,051 objects in both groups. It excluded 527 objects for a detected data-centre identity and 5,850 for an unstable lifecycle; exclusion categories can overlap. Another 1,351,793 broad grid objects lacked a parsed voltage at or above 110 kV.

The frozen directory is mode `0555` and contains exactly five mode-`0444` files:

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `stable-industrial-grid.osm.pbf` | 400,046,048 | `c42666f82c32d72a5452df9d0d84de3d6fb5562cbdb9dbecb3d64f407821c50d` |
| `selection-ledger.jsonl` | 285,472,275 | `261869a41627e1b91b6ca08a31890185521e05c5ca36a4bbd987fad324ad2eed` |
| `selected-feature-ids.txt` | 25,674,929 | `e76a30ed650908b998b54f904437f1782ccf3ae5319da303dd6001f5a40fe8f9` |
| `extract-manifest.json` | 11,645 | `8c355835c24b2eb584d5f77cbaf1d314a3f27c128ac7a7816f5d7394f5a175e4` |
| `manifest.sha256` | 88 | `b133c5401ef1932b5c435383f83ce9c2039b6211784a3f2aafb360481d0b693f` |

The path/size/SHA-256 inventory digest is `a97e8a19b554f4a4e15b66d42fe0fc825e34f791cf2f8ce504cda269636db433`. The extraction began at `2026-07-19T09:02:02Z` and completed at `2026-07-19T09:35:12Z`. The manifest pins osmium-tool 1.19.1, the Python/runtime record, exact commands, code bytes, selection statistics, source acquisition record, PBF file information, and output hashes.

## Rights, limitations, and verification

OpenStreetMap data is ODbL 1.0. Preserve `© OpenStreetMap contributors` and the official copyright link. The derivative's candidate-independence does not make it independent corroboration of other OSM-derived sources.

The extraction deliberately removes known data-centre labels so the blind sample can audit discovery misses. That exclusion is not linguistically complete, and stable industrial/grid context is neither a negative nor positive data-centre finding. Geometry quality, tagging completeness, voltage parsing, lifecycle tagging, and snapshot freshness remain source limitations. The downstream producer must still compute valid union/intersection/distance geometry and independently reproduce its normalized streams before any production blind frame is allowed.

Offline verification first checks the frozen derivative and can optionally avoid rereading the 93.9 GB source. The second command independently recomputes the complete source SHA-256:

```bash
python3 scripts/extract_osm_blind_tile_auxiliary.py --verify-only --skip-deep-source-hash
python3 scripts/extract_osm_blind_tile_auxiliary.py --verify-only
python3 -m unittest tests.test_osm_blind_tile_auxiliary
```

