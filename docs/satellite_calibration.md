# Historical Sentinel v1 analyst-review audit

The frozen bundle at `satellite_calibration/2026-07-18-analyst-reviews-v4` audits the 43 Sentinel
report/review pairs pinned by `sources/candidate-fusion-2026-07-18-osm-planet-v13.json`. Every input
report uses algorithm `sentinel-2-l2a-change-v1`; this is a historical descriptive audit, not a
calibration of the current v2 processor. The definition pins the candidate-fusion v13 definition
and manifest plus the byte count and SHA-256 for each input report and review, but its frozen row
schema does not carry the algorithm-version field explicitly.

## Recorded fields

Each JSONL and CSV row records the queue ID, source run, entity, MGRS tile, scene dates, STAC item
hashes, input paths and hashes, analyst decision, and simplified outcome. The calibration schema
version is not the change-algorithm version. Each row also carries the full numeric metric block:

- valid-pixel fraction;
- filtered proposal component count, area, and fraction of valid pixels;
- mean absolute reflectance change;
- mean baseline and current NDVI;
- mean NDVI change;
- mean NDBI change.

`summary.json` reports count, minimum, mean, median, and maximum for each metric across the 43 rows
and for each outcome. The JSONL supplies the row-level distribution.

## Descriptive rules

The definition retains five predeclared audit anchors: any filtered component, filtered proposal
area of at least 10,000 or 50,000 square metres, and proposal fraction of at least 1% or 5%. The
summary crosses each rule result with the retain and reject labels. The calibration does not search
for a threshold or select a production rule.

## Claim boundary

The 43 reviews form a selected v1 follow-up set. Analysts assigned site-aligned follow-up labels
after manual inspection of comparison PNGs. Those labels do not establish pixel truth,
construction truth, or accuracy outside this set. The sample has no recall denominator. Two
active-lane inputs, queue positions 27 and 60, used clipped selected-asset coverage. Removing those
two labels would not turn the remaining records into a v2 calibration: all 43 require current-v2
reprocessing and fresh review before current-processor performance can be estimated.

The scope keeps identity, lifecycle, operating status, type, workload, power, and energy promotion
flags false. It also keeps automatic merge and production-threshold flags false. The bundle copies
no raw PNG, GeoJSON proposal, raster, or other imagery artifact and reports no unique-site count.

## Offline reproduction

Run this command from the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/build_satellite_calibration.py \
  --definition sources/satellite-calibration-2026-07-18-analyst-reviews-v4.json \
  --output satellite_calibration/2026-07-18-analyst-reviews-v4 \
  --validate-only
```

The validator derives all payload and manifest bytes from the pinned local inputs. A build to a new
destination writes through a sibling staging directory, validates the closed file set, renames the
directory, sets the directory to `0555`, and sets all seven files to `0444`. The builder refuses an
existing destination.

## Pinned v4 result

V4 contains 43 algorithm-v1 report/review pairs: seven from the active lane, one from the proposed
lane, 23 from Unknown010, six from Unknown013, and six from Unknown015. Analysts marked 12 for
follow-up and rejected 31 automated masks for site promotion. These labels do not calibrate v2.

| Rule | Reject - | Reject + | Retain - | Retain + |
| --- | ---: | ---: | ---: | ---: |
| Any filtered component | 2 | 29 | 0 | 12 |
| Proposal area at least 10,000 m2 | 3 | 28 | 0 | 12 |
| Proposal area at least 50,000 m2 | 8 | 23 | 0 | 12 |
| Proposal fraction at least 1% | 5 | 26 | 0 | 12 |
| Proposal fraction at least 5% | 24 | 7 | 7 | 5 |

These counts describe the selected historical-v1 set and do not promote any atlas claim. A
successor audit must record the change algorithm and selected-asset coverage status per row rather
than mutating this frozen bundle.

Pinned SHA-256 values:

- candidate-fusion v13 definition: `63b02b886c83e6b2d9de739f0acb85a566f03d4338796b2a546ddc34cbd3de33`;
- candidate-fusion v13 manifest: `12fc7517e5fdb4e00c2a7e59c069d868801ac87ecbc8c0237433b65e51ab9cc9`;
- calibration definition: `876d88ff2c8ad137799714408b39016bf10b12820f637c3c2ff9ab3f30283414`;
- calibration manifest: `a3b153c97286a9c93a2b654f427fabdb1bffafc950dc0e6a6ba5c1bdf9ff1c41`;
- summary: `6b8261b0f8040c156283f530232ac969ec079cd8b298bdde5b84ab638e331a0f`;
- JSONL: `9242f98e2ecf75c4e98cff6d28c4416798f8261aa8c5f0ab13f1e358250d4376`;
- CSV: `22019c683c9b28d9bbe7ba01f8af7194a37ac47f473b58638d62c3cd0745b0ce`.

V1, v2, and v3 remain frozen historical checkpoints and reproduce from their pinned inputs.
