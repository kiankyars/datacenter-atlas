# Satellite catalog coverage reselection v2

This is a new generalized carrier. It does not edit, reinterpret, or replace
`satellite_catalog_reselection.py` or the frozen v1 release. V1 remains the
historical 2026-07-19 edge-audit lineage with its fixed ID inventory. V2 accepts
an explicit repeatable candidate inventory so a later queue can be assessed
without changing that history.

## Contract

Every `--queue-id` must exist in the validated queue and have a `completed`
source catalog task in the validated source batch. Repeated flags may be passed
in any order, and duplicate occurrences are harmless: the manifest records one
deduplicated inventory in canonical queue-position order.

For every candidate, v2 verifies that the source-selected pair genuinely fails
the complete required-asset read window, including interpolation-support pixels.
It then filters the exact archived baseline and current STAC FeatureCollections
to full-cover features and evaluates chronological comparable pairs on one red
grid. The deterministic ranking remains:

1. same known MGRS tile;
2. closest season;
3. lowest combined cloud cover;
4. closest target dates;
5. stable timestamps and item IDs.

If a comparable pair exists, v2 emits one supported reselection. Otherwise it
emits an explicit
`unresolved_multitile_or_supplemental_scene_required` record. That outcome is
not a no-scene claim and does not authorize an unarchived companion tile.

Catalog availability and coverage are workflow evidence only. Neither a
supported nor unresolved assessment establishes visible change, identity,
lifecycle, construction status, operating status, operator, facility type,
capacity, load, energy, PUE, workload, tenant, or unique-site identity.

## Three separate steps

The header capture is the only network-capable step. It opens metadata for the
unique assets of supported selected pairs only. The code issues no dataset
`read` call and records `pixel_reads: 0`; an asset-open count is deliberately
not described as an HTTP-request count. Header evidence binds the canonical
candidate IDs, queue and source-batch hashes, source task hashes, original and
selected IDs, selected feature hashes, and an overall plan hash.

```sh
python3 scripts/build_satellite_catalog_reselection_v2.py capture-headers \
  --queue-dir satellite_review_queues/2026-07-20-open-seed-v43 \
  --source-catalog-batch-dir satellite_review_runs/2026-07-20-open-seed-v43-active-001 \
  --queue-id satq-d0a872a7aee9f9f54a8631ef \
  --queue-id satq-cef871428da247c3ecfadec6 \
  --output-file /an/explicit/new/grid-headers-v2.json \
  --captured-at 2026-07-20T00:00:00Z
```

Capture output must be a new path. The example order is intentionally reversed;
the resulting candidate inventory is positions 4 then 6.

Build is offline. It accepts only the exact bound header evidence, copies raw
provider responses and source manifests byte-for-byte, writes into a sibling
staging directory, reproduces the release, fsyncs it, freezes files to `0444`
and directories to `0555`, validates the frozen tree, and atomically renames it
to the unused output path.

```sh
python3 scripts/build_satellite_catalog_reselection_v2.py build \
  --queue-dir satellite_review_queues/2026-07-20-open-seed-v43 \
  --source-catalog-batch-dir satellite_review_runs/2026-07-20-open-seed-v43-active-001 \
  --queue-id satq-cef871428da247c3ecfadec6 \
  --queue-id satq-d0a872a7aee9f9f54a8631ef \
  --grid-header-evidence /an/explicit/new/grid-headers-v2.json \
  --output-dir satellite_catalog_reselection_runs/AN-UNUSED-V2-NAME \
  --generated-at 2026-07-20T00:00:00Z
```

Validation is also offline and requires the same explicit candidate set. It
recomputes the plan from the frozen queue and source batch, checks the complete
closed tree, exact source copies, capture lineage, canonical JSON, builder and
runtime hashes, immutable modes, unresolved assessment, per-job manifests, and
top manifest.

```sh
python3 scripts/build_satellite_catalog_reselection_v2.py validate \
  --queue-dir satellite_review_queues/2026-07-20-open-seed-v43 \
  --source-catalog-batch-dir satellite_review_runs/2026-07-20-open-seed-v43-active-001 \
  --queue-id satq-cef871428da247c3ecfadec6 \
  --queue-id satq-d0a872a7aee9f9f54a8631ef \
  --release-dir satellite_catalog_reselection_runs/AN-EXISTING-FROZEN-V2-RELEASE
```

These commands are documentation, not evidence that a capture or release has
been executed. A release must not be published until its header capture and
frozen output have been independently reviewed.
