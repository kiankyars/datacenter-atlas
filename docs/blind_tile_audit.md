# Candidate-independent blind global tile audit

The blind-tile lane is the missing-site audit. It samples land without consulting any known data-centre candidate, Atlas release, construction ledger/map, satellite queue, OSM structural shortlist, or candidate-fusion output. Its purpose is to measure what a candidate-led discovery stack can miss; a selected tile is not evidence that a data centre exists there.

## Frozen design

The production frame is an integer-indexed 4 km grid in EPSG:6933 with origin `(0, 0)`. A tile ID is a pure function of its signed integer x/y indices. Eligibility requires a positive projected-area intersection with the union of non-Antarctic land from the pinned Natural Earth 1:10m Admin-0 Countries v5.1.1 artifact. Zero-area boundary touches are ineligible.

Every positive Natural Earth country overlap is retained. The assigned country is the greatest projected overlap, with lexicographic `country_key` as the tie-break. Country overlaps are aggregated to six macroregions—Africa, Asia, Europe, North America, South America, and Oceania—and the assigned macroregion uses the same greatest-overlap rule with a lexical tie-break. These assignments are sampling labels, not source claims about a data centre.

Each eligible tile belongs to exactly one stratum:

- `background`: no urban, industrial, or grid signal.
- `urban_built`: urban, with neither industrial nor grid.
- `industrial_xor_grid`: exactly one of industrial or grid; urban may coexist.
- `industrial_and_grid`: both industrial and grid; urban may coexist.

Urban means GHS-BUILT-S 2020 built surface is at least 0.5% of tile land area, or GHS-SMOD identifies an urban cluster. Industrial means at least 10,000 m² overlap with a frozen stable-OSM industrial auxiliary after excluding construction/proposed features and data-centre structured tags or phrases in the pinned multilingual exclusion lexicon. Unlisted localized names remain an explicit leakage blocker rather than a completeness claim. Grid means a frozen stable-OSM substation, line, or cable auxiliary lies within 5 km and has parsed voltage of at least 110 kV, after excluding proposed/construction features. An unknown auxiliary signal is treated as false and remains in the lower stratum; it is also retained as an explicit unknown field.

The per-macroregion quotas are 16 background, 24 urban, 40 industrial-xor-grid, and 80 industrial-and-grid tiles: a ceiling of 160 per macroregion and 960 globally. If a stratum has fewer tiles than its quota, it is a census and unused quota is not reallocated.

The fixed seed string is `datacenter-atlas-blind-tile-audit-v1|frame-2026-07-19`, whose SHA-256 is `8dfad5fa219214e8031b70e831b9ccf45d881b32066051775417f0651f651e3f`. The draw key is `SHA256(ASCII(seed_sha256) || NUL || ASCII(tile_id))`; rows are ranked by draw key and then tile ID. Each selected row retains the exact unreduced inclusion probability `n_h/N_h` and design weight `N_h/n_h` for its macroregion-by-stratum cell.

## Three immutable bundles

The design separates three stages so later imagery or analyst decisions cannot rewrite the sample:

1. **Frame/sample bundle (implemented):** `definition.json`, `frame-cells.jsonl.gz`, `strata.json`, `sample.jsonl`, `coverage.json`, `README.md`, `ATTRIBUTION.txt`, `manifest.json`, and `manifest.sha256`.
2. **Imagery execution bundle (not implemented):** would pin the frame manifest, imagery catalog/items and legal notices, cloud/valid-pixel gates, model/runtime/processor lineage, per-tile execution status, and machine proposals. It may not change sample membership or infer data-centre identity/status/type/capacity, power, energy, or PUE.
3. **Analyst audit bundle (not implemented):** would pin both earlier manifests, a predeclared review protocol, independent labels and adjudication, exclusions/nonresponse, and weighted estimates using the frozen `n_h/N_h`. It may not silently promote review labels into the construction master.

## Checked-in preflight, not the global frame

`blind_tile_frames/blind-tile-frame-preflight-2026-07-19-v1` is a synthetic contract preflight. It exercises all six macroregions, all four strata, overlap retention, equal-area country tie-breaks, selection above every quota, exact probabilities/weights, deterministic gzip/JSON bytes, and immutable validation. Its cells have no geographic meaning.

The frozen definition SHA-256 is `7ac8dbb38e2c7e30d891e460d4e93af198125f2e3ac3dc593be6a1ccb5a6b812`; the frozen bundle manifest SHA-256 is `7517e133339d529d019229ee1d58cc2a06fb46cbfd82c7c00b46af0bba121af5`.

The pinned Natural Earth artifact is present and hash-valid, but its geometry was not applied to the fixture. The official GHS-BUILT-S 2020 and GHS-SMOD 2020 1 km archives are present in a separately frozen, hash-bound cache; their area-conserving/categorical integration into EPSG:6933 remains deferred and was not applied to this historical preflight. The [full-Planet stable OSM industrial/grid derivative](osm_blind_tile_auxiliary.md) is now frozen from the official 2026-07-13 snapshot with 2,271,713 selected objects, but it also was not applied to the preflight. The raw-source-to-normalized-stream geometry producer and its independent recomputation validator remain unimplemented, so no production land frame or production sample was built. `coverage.json` remains the immutable preflight record of its original blockers and explicitly rejects completeness, recall, and competitive-parity claims.

The builder reads only the definition, the pinned Natural Earth artifact, and a hash-pinned synthetic fixture specification. A regression test changes an isolated candidate-fusion decoy between two builds and requires every output byte to remain identical. Definition input paths containing construction-master/map, satellite-queue, OSM-structural-shortlist, candidate-fusion, or Atlas-artifact references fail closed.

Build and validate offline:

```bash
python scripts/build_blind_tile_frame.py
python scripts/validate_blind_tile_frame.py
python -m unittest tests.test_blind_tile_frame
```

No network request is made by either command.
