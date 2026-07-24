# Construction evidence map

`datacenter_atlas.construction_map` projects the frozen construction-master ledger into a
browser map. The public-open v11 release maps 108,972 of 109,063 observation rows. Ninety-one rows
lack coordinates and remain outside the index.

The rows are source observations, not unique physical sites. The map does not merge entities,
recompute construction arithmetic, promote review or discovery rows, or create construction
claims. The unique physical-site count remains null.

## Coverage

| Evidence tier | Mapped observations | Default visibility |
| --- | ---: | --- |
| Tier A | 198 | Visible |
| Tier B | 6,280 | Visible |
| Tier C | 102,494 | Hidden |
| Total | 108,972 | 6,478 visible by default |

All 46 v11 Tier-A additions are coordinate-null, so the mapped count and 6,478-row default Tier A+B
view remain unchanged from v10. The new rows include 24 planned critical-IT observations, one
contracted grid-connection observation, one broad AI workload, and one retail-colocation operating
model; none is mapped by inference. The map does not present locality labels as parcels or facility
footprints or convert planned or contracted values into current load. The shared CoreWeave
Ellendale row continues to carry the sole source-supported operating-model observation in the
mapped index; the new Equinix DB7x observation remains unmapped.

The strict map definition records all 91 unmapped `source_record_id` values. They comprise 73 Tier-A
rows, all four France IGEDD rows, all three New Zealand rows, one Netherlands row, one England row,
and nine SEC leads. For example, the following French IGEDD rows have null latitude and longitude
in the master and stay unlocated in the map:

- `fr-igedd-ae-2021-104`
- `fr-igedd-ae-2024-08`
- `fr-igedd-ae-2025-058`
- `fr-igedd-ae-2026-33`

The projection does not geocode or infer coordinates for any missing row.

## Strict release contract

The canonical definition is
`sources/construction-map-2026-07-19-public-open-v11.json`. Both the builder and validator consume
it. The definition pins:

- the master ID, directory, definition, JSONL, and manifest;
- the map ID, timestamp, schema, and scope;
- the browser template path, byte count, and SHA-256 digest;
- the exact master, mapped, unmapped, default-visible, and per-tier counts;
- the exact ordered set of unmapped source record IDs.

Any changed path, byte checkpoint, count, tier assignment, missing ID, or scope field fails the
strict build. The release directory has mode `0555`; its seven files have mode `0444`.

## Bundle contents

- `construction-map-index.json.gz` contains the deterministic compact row projection.
- `construction-map.html` embeds the same compressed bytes as base64.
- `coverage.json` records mapped and unmapped totals plus country, status, kind, source, and tier
  distributions.
- `manifest.json` and `manifest.sha256` pin the master ledger, template, and output bytes.
- `README.md` states the release boundary.
- `ATTRIBUTION.txt` retains source and basemap attribution.

The canvas renderer draws the discovery layer without creating one DOM node per point. Filters
cover evidence tier, source status, country, and record name. The detail pane retains source and
license fields, the construction-verification boundary, capacity and energy observations,
evidence dates, and advisory-link counts.

## Build and validate

Run these commands from `datacenter_atlas`. The build destination must not exist.

```sh
python3 scripts/build_construction_map.py \
  --master-dir construction_master/2026-07-19-public-open-v11 \
  --master-definition sources/construction-master-2026-07-19-public-open-v11.json \
  --map-definition sources/construction-map-2026-07-19-public-open-v11.json \
  --output-dir /path/to/new/2026-07-19-public-open-v11

python3 scripts/validate_construction_map.py \
  --map-dir construction_maps/2026-07-19-public-open-v11 \
  --master-dir construction_master/2026-07-19-public-open-v11 \
  --master-definition sources/construction-master-2026-07-19-public-open-v11.json \
  --map-definition sources/construction-map-2026-07-19-public-open-v11.json
```

Validation and reproduction make no network requests. Deterministic gzip output uses `mtime=0`
and pins header byte 9 to the RFC 1952 unknown-platform value `255`. The frozen bundle was rebuilt
independently in a second local directory and all seven files were byte-identical; the strict
validator also reproduced every byte offline.

## Projection checks

Offline index and strict-definition checks confirmed:

- default Tier A+B: 6,478 visible observations;
- all tiers: 108,972;
- Tier A: 198; Tier B: 6,280; Tier C: 102,494;
- status `Under Construction`: 147;
- country `Germany`: 29;
- the exact 46-row v11 Tier-A delta is present in the master and explicitly absent from the mapped
  index because every source row lacks coordinates.

The embedded observation index needs no API or data fetch. Browser display loads D3, TopoJSON,
Pako, and the Natural Earth-derived `@d3-maps/atlas` basemap from the named CDNs.

## Release checksums

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `construction-map-index.json.gz` | 6,655,195 | `b75c4142f5752a8dd058ea63dd598127848c34e7a4455b2cd66f2405c12e8e28` |
| `construction-map.html` | 8,891,434 | `dd7b815cf077a310d84855c218aece7f0212b7cb862806508b82747c7ab6c17e` |
| `coverage.json` | 6,235 | `7b19c8a4303fe3b75e6075cf5d8b3167bbce22527de38ecbbb0e924ce68c2d3e` |
| `README.md` | 359 | `c4e8efe625a03f541a8dd081e25d78d1d028ad5f5193ad1e2b5e4cb2ee16e73f` |
| `ATTRIBUTION.txt` | 273 | `e45de5af520e43590bf4adeab0fe47c803c949f445b09e8cfeedf3cdf3039be3` |
| `manifest.json` | 1,967 | `e9aa6e9778edba365572eb92bc87b0612e6daf1f02387eac96046c935ce2c56c` |

The uncompressed index has 67,356,969 bytes and SHA-256
`352474ff2f100a6610f9ba679ff12b8ed605bdbe04c1f3a2766c12ca8530d271`.

The v1 through v10 map definitions and frozen bundles remain byte-for-byte historical artifacts.
