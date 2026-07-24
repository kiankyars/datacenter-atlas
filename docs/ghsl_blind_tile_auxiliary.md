# GHSL blind-tile auxiliary

The pinned pair is the official GHSL R2023A 2020 1 km release: GHS-BUILT-S V1.0 and the GHS-SMOD L2 V2.0 settlement model. This is deliberately a bounded auxiliary screen for the 4 km blind frame, not a facility or data-centre detector. The much larger 100 m BUILT-S archive (publisher index display approximately 1.9 GB) was not downloaded.

## Exact inputs

| Product | Official artifact | Publisher index display | Exact bytes | Local SHA-256 |
| --- | --- | ---: | ---: | --- |
| GHS-BUILT-S 2020, 1 km, V1.0 | `GHS_BUILT_S_E2020_GLOBE_R2023A_54009_1000_V1_0.zip` | `145M` | 152,527,564 | `5ab899936b560f1b803778fffe6912a28de50036e2bfa0338d55ed34e502d8a2` |
| GHS-SMOD 2020, 1 km, V2.0 | `GHS_SMOD_E2020_GLOBE_R2023A_54009_1000_V2_0.zip` | `34M` | 35,853,870 | `5a81c3827c9bbc9109159b4c3f92ac7722705944e43038219f142b410431a852` |

The exact official URLs, HTTP response metadata, four GETs, zero redirects, and ZIP member CRCs are in `source_cache/ghsl-r2023a-2020-1km/fetch-manifest.json`. The publisher did not advertise an archive checksum in the product directories. Accordingly, the SHA-256 values above are locally computed byte pins, not publisher checksums. Both archives passed full local ZIP CRC/decompression validation.

The product catalogue records are:

- GHS-BUILT-S: `https://data.europa.eu/89h/9f06f36f-4b11-47ec-abb0-4f8b7b1d72ea`, DOI `10.2905/9F06F36F-4B11-47EC-ABB0-4F8B7B1D72EA`.
- GHS-SMOD: `https://data.europa.eu/89h/a0df7a6f-49de-46ea-9bde-563437a6e2ba`, DOI `10.2905/A0DF7A6F-49DE-46EA-9BDE-563437A6E2BA`.

## Embedded raster contract

Both TIFFs are global rectangular World Mollweide grids with 36,082 columns, 18,000 rows, 1,000 m pixels, bounds `[-18041000, -9000000, 18041000, 9000000]`, and an area-based pixel interpretation. GDAL resolves the embedded CRS to `ESRI:54009`; references to “EPSG:54009” in publisher prose should not be copied as an EPSG-authority identifier.

BUILT-S is one `uint32` band reporting predicted built-up square metres per grid cell, with nodata `4294967295`. SMOD is one `int16` L2 band with nodata `-200`; the observed codes are `10, 11, 12, 13, 21, 22, 23, 30`. The blind-frame urban screen uses the predeclared urban codes `{21, 22, 23, 30}`.

The complete embedded metadata and streamed value counts are frozen in `raster-metadata.json`. The resumable aggregation and validation core is implemented and synthetic-fixture tested, but production geometry normalization and integration remain unexecuted:

- Reproject source-cell and target-tile boundaries into EPSG:6933 before measuring area. A tile's denominator is exactly its positive-area intersection with the pinned union of non-Antarctic Natural Earth land.
- BUILT-S values are extensive square-metre totals, not an intensive field. Convert each valid integer-square-metre source total to integer square millimetres, then allocate it among target tiles in proportion to each tile-land/source-cell intersection divided by that source cell's non-Antarctic land-intersection area. Apply floor division and assign residual square millimetres by deterministic largest remainder, breaking ties by tile ID. Never use bilinear interpolation. Require exact per-source and global integer conservation before accepting output.
- The BUILT-S signal is true when the conserved allocated total is at least 0.5% of tile land area. It is false only when the relevant tile-land coverage is fully valid and the total is below threshold. If nodata or incomplete source coverage prevents that false determination, retain explicit `unknown`; never substitute zero. A known lower bound already at or above threshold may still establish true.
- SMOD remains categorical. Compute exact positive-area intersections of the original source-cell footprints with tile land; the urban code set is exactly `{21, 22, 23, 30}`. The SMOD signal is true when summed urban-coded intersection area is greater than zero. It is false only when the entire tile-land area is covered by valid non-urban SMOD cells and urban-coded area is zero. Otherwise it is explicit `unknown`. If any raster resampling is used only as an implementation aid, it must be nearest-neighbour and must reproduce the cell-intersection classification.

The production run remains deferred, so no production frame or sample-size claim is made. The executable aggregation contract and its additional fail-closed gates are documented in `blind_tile_auxiliary_integration.md`.

## Rights and reproducibility

The exact 540-byte notice from each official product directory states CC BY 4.0: credit is required and changes must be indicated. Use “European Union / European Commission, Joint Research Centre (JRC)” and link `https://creativecommons.org/licenses/by/4.0`.

The controlled acquisition made exactly four GETs: two archives and two copyright notices. Before it, direct research probes made two archive HEAD requests and two copyright GET requests. Thus the known direct total across probing and acquisition is eight requests: two HEAD and six GET. Browser-assisted product, catalogue, and directory research is outside that count. Its exact origin-request total is unknowable because the browsing service does not expose origin/cache/redirect accounting, so this bundle does not claim an exact all-origin total. The embedded Data Package PDF remains inside each archive and was not reviewed to derive additional claims.

Offline verification:

```bash
python scripts/fetch_ghsl_blind_tile_auxiliary.py --verify-only
python -m unittest tests.test_ghsl_blind_tile_auxiliary
```
