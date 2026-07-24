# Deterministic satellite-review queue

The queue builder turns an existing release `atlas.geojson` into bounded review jobs for
`scripts/catalog_satellite.py` and `scripts/sentinel_change.py`. It is an offline planner: building
the queue performs no catalog calls, reads no imagery, changes no entity status, and infers neither
facility identity nor power.

```sh
python3 scripts/build_satellite_review_queue.py \
  --input releases/2026-07-17-open-seed/atlas.geojson \
  --output-dir satellite-review-queue \
  --generated-at 2026-07-18T22:00:00Z \
  --baseline-target 2024-06-15 \
  --current-target 2026-06-15
```

The explicit generation timestamp and target dates keep reruns reproducible. Defaults use a 2 km
half-side AOI, ±45-day independently bounded catalog windows, 20% maximum scene-level cloud cover,
and the existing 5,000 m² change-component floor. These are planning parameters, not claims about a
site.

## Selection and ordering

Only coordinate-bearing campuses, facilities, and projects are queued. Buildings are excluded to
avoid automatically multiplying site reviews by every source building footprint. Projects remain
separate entity-level jobs when present; the builder does not merge a project with its target.
Entities lacking both property coordinates and usable GeoJSON geometry are counted and skipped.

Lifecycle defines the primary priority tier:

1. active construction, detailed physical construction stages, commissioning, and expansion;
2. proposed pipeline states from lead/announcement through permitted;
3. unknown lifecycle;
4. operational;
5. paused, cancelled, repurposed, decommissioned, or demolished.

Within a tier, records with no `status_as_of` come first, followed by known statuses from oldest to
freshest relative to the release `atlas_as_of`; entity ID and AOI part number break ties. Every job
stores the canonical status date, its non-negative age in days at `atlas_as_of`, and an explicit
missing flag. The manifest reports fixed missing, 0–30, 31–90, 91–180, 181–365, and 366-plus-day
buckets. Invalid or future status dates fail closed. This secondary policy reduces stale coverage
first without changing any lifecycle rank.

Capacity, workload, operator, and imagery-derived values do not affect priority. Unknown input enum
values fail closed rather than silently receiving a rank. Each queued entity also preserves the
release's effective `country`, `country_iso_a2`, and `country_iso_a3` fields—not source-country tags.
ISO fields may be null for unmatched records; non-null values must be uppercase alpha-2/alpha-3.
The manifest supplies an entity-level country-by-priority-tier cross-tab so regional balance can be
audited without counting antimeridian-split jobs twice.

## Artifacts and batching

The output directory is a closed bundle containing exactly:

- `satellite-review-queue.jsonl`: one canonical JSON object per bounded AOI job;
- `manifest.json`: exact input hash, configuration, priority policy, coverage/skipped counts, and
  the queue artifact byte count and SHA-256;
- `manifest.sha256`: SHA-256 of the exact manifest bytes.

`validate_queue_bundle(path)` verifies the exact three-file set; regular-file boundaries; exact
manifest sidecar; canonical manifest and JSONL encoding; queue bytes, hash, and record count;
schema, contiguous positions, unique deterministic IDs, AOI parts, ordering; and reconciliation of
kind, tier, country/tier, and freshness counts. An extra file or any byte-level or semantic tamper
invalidates the whole bundle.

If the input `atlas.geojson` has an adjacent release `manifest.json`, publication first verifies the
release manifest's recorded atlas byte count and SHA-256. The queue manifest then records the exact
release-manifest byte count and SHA-256 as lineage in addition to the atlas hash. A present but
invalid, mismatched, or non-binding release manifest is an error; it is never silently ignored.

First publication writes a private sibling staging directory, validates it completely, and performs
one directory rename. A rerun against an existing output succeeds only when the existing bundle is
valid and all three files are byte-identical. Invalid or valid-but-different output is refused and
left untouched; choose a new output directory for a new timestamp, source, or configuration.

Each queue row contains an argument array that can be passed to `catalog_satellite.py`. The
[resumable batch runner](satellite_batch.md) validates the complete queue bundle, runs those catalog
jobs under explicit request budgets, and stores its checkpoints in a separate execution directory.
It is catalog-only and does not execute change analysis. Each row also retains a
`sentinel_change.py` argument template for a later reviewed workflow; that workflow must resolve
`{selected_ids.baseline}` and `{selected_ids.current}` from the validated catalog manifest before
use. Job paths are relative to the separate execution directory.

AOIs crossing ±180° are split into two non-wrapping jobs because the existing catalog and change
CLIs each accept one ordinary WGS84 bbox. Both jobs retain the same entity reference and explicit
part count. This preserves coverage without inventing a geometry merge.

Every row repeats the hard review constraints: the atlas entity/location is the queue basis; imagery
creates review evidence only; identity, lifecycle, operating status, and power claims are all false;
analyst review is required.
