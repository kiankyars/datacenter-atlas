# Microsoft Global ML Building Footprints lane

This lane provides a lawful global shard inventory and a small building-footprint
review pilot. It does not identify data centres. Microsoft publishes the data
under CDLA Permissive 2.0; the exact upstream license file and source metadata
are retained in the frozen bundle.

## Pinned upstream state

- Official index: `https://minedbuildings.z5.web.core.windows.net/global-buildings/dataset-links.csv`
- Index checkpoint: 7,171,802 bytes, SHA-256
  `9371e9fd27f1e82856b2ed7a3c0397c685ee0396b1078a0af77dbe91269f9be6`,
  Content-MD5 `w6gdmnq4V62aXuO+HCl78w==`
- Index metadata: Last-Modified `Wed, 25 Feb 2026 23:01:46 GMT`, ETag
  `"0x8DE74C1D9A45909"`
- Repository commit:
  `ef94ee3dfb5da3bd2c9dd9c36815eff66fa0b66d`
- Pinned repository README: 19,885 bytes, SHA-256
  `ca28c105aecc8082406983549c2eada07fd107ad201cf2aa89695132ea367760`
- Pinned repository license file: 81 bytes, SHA-256
  `24903c0990deb68027170143067d680302cfa0056f71020a905dccba21f815a1`

The global inventory contains 30,344 unique `Location + QuadKey` rows, 30,344
unique URLs, and 225 locations. Summing the rounded human-readable size labels
with the index's binary-unit convention gives approximately 122,423,557,613
compressed bytes. This is an index inventory, not a download or validation of
all global geometry and not a global completeness claim.

## Selective pilot

The pilot uses only country-specific shards and excludes the overlapping
continental rows. Each AOI is a roughly 2 km by 2 km box centred on an exact,
hash-pinned construction-master record.

| Pilot | Country shard | Compressed bytes | Shard features | AOI review footprints |
|---|---:|---:|---:|---:|
| M24 | Iceland `031013111` | 944,066 | 7,280 | 266 |
| DayOne Nusajaya | Malaysia `132232213` | 22,707,814 | 248,428 | 258 |
| Start Campus Sines | Portugal `033110213` | 4,348,696 | 51,087 | 116 |
| Stargate UAE | UnitedArabEmirates `123023301` | 16,897,881 | 170,194 | 31 |
| Total | 4 country shards | 44,898,457 | 476,989 | 671 |

All 671 selected footprints carry the upstream `-1` missing sentinel for height
and confidence. The lane preserves those values as raw source attributes and
maps them to null interpreted values. It does not impute either field. The UAE
shard has 468 confidence-bearing features outside the selected AOI; that does
not change the selected-row count.

The upstream `.csv.gz` files contain gzip-compressed, line-delimited GeoJSON.
The bundle records each compressed and decompressed shard hash, the exact source
line number and hash for every selected feature, original geometry, approximate
footprint area, derived centroid, bounding box, and distance to the construction
prior's point.

## Inference boundary

Every review row is non-merging. A building footprint, height, confidence, or
proximity to a construction prior establishes none of the following:

- data-centre identity or a unique site;
- lifecycle, construction, or operating status;
- data-centre type or workload;
- IT capacity, gross facility power, PUE, or annual energy;
- an independent evidence family for the source-reported construction record.

Those Atlas fields remain explicitly null. Manual imagery and documentary
review is required before any separate evidence can affect an Atlas entity.

No per-feature imagery or inference date is supplied. The pinned upstream
README describes imagery spanning 2014-2024 in the dataset introduction and
some 2026 updates derived from 2021-2025 imagery. Neither range is assigned to a
selected country shard or footprint without separate evidence. Upstream also
documents geographic quality variation and missing tiles.

## Reproduction and validation

The source definition is
`sources/microsoft-global-ml-building-footprints-2026-07-18-v1.json`. Fetching
uses seven bounded HTTPS requests: the index, pinned license, pinned README, and
four selected shards. Every response body must match the definition's byte and
SHA-256 checkpoint before derivation.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
  python3 scripts/fetch_microsoft_building_footprints.py \
  --output source_cache/microsoft-global-ml-buildings-2026-07-18-v1
```

Inventory an already downloaded index without network access:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
  python3 scripts/inventory_microsoft_building_footprints.py \
  --index source_cache/microsoft-global-ml-buildings-2026-07-18-v1/dataset-links.csv
```

Validate the closed file set, exact permissions, manifest sidecar, every file
hash, source semantics, and byte-for-byte offline reproduction:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
  python3 scripts/validate_microsoft_building_footprints.py
```

The published directory is mode `0555`; every contained file is mode `0444`.
Validation performs zero network requests and rejects extra files, permission
changes, source tampering, derived-row promotion, or a changed definition.
