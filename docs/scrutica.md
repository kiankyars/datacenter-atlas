# Scrutica isolated discovery layer

Snapshot contract: 2026-07-18. Scrutica's public directory is a mixed compute-infrastructure
inventory, not a list of 4,234 data centres. It reported **4,550 tracked records**, of which
**4,234 were individually browsable** across **85 pages** and **316 licensed-source rows were
present only in aggregate counts**. Those 316 rows are not facility tasks and are never silently
represented as covered records.

The hash-pinned 4,234-row directory exposed this exact `facility_type` distribution:

| Scrutica `facility_type` | Rows | Atlas default |
| --- | ---: | --- |
| `colocation` | 2,025 | Import |
| `hyperscale_dc` | 1,552 | Import |
| `ai_training` | 521 | Import |
| `other` | 91 | Exclude; review required |
| `hpc_center` | 21 | Import |
| `logic_fab` | 14 | Exclude; not a data centre |
| `packaging` | 6 | Exclude; not a data centre |
| `memory_fab` | 3 | Exclude; not a data centre |
| `edge` | 1 | Import |

The versioned default policy therefore imports **4,120 explicit data-centre rows** and excludes
**114 rows**: 23 fabs or packaging facilities and 91 ambiguous `other` records. Missing, novel,
or differently cased type values also fail closed as unknown. The importer never guesses scope
from a facility name or description. There is no command-line override that can place excluded
records into a Data Center Atlas release; changing the allowlist requires an explicit, source-backed
policy revision. All excluded records remain intact in the raw fetch bundle for review.

Scrutica presents its directory under CC BY-SA 4.0, except where a record identifies different
source-specific terms. That label does not itself establish that an upstream source authorized
Scrutica or Atlas redistribution. The share-alike and upstream-rights boundary is intentionally
separate from the atlas's ODbL/CC0/open-source release database:

- use a dedicated SQLite file and a dedicated release for Scrutica;
- do not import Scrutica into `atlas.sqlite` or any ODbL/CC0 combined release;
- retain the canonical Scrutica facility URL, publisher, CC-BY-SA attribution, upstream
  `data_source`/`source_url`, estimate flag, authority tier, and vintage;
- compare Scrutica facilities with open-source entities only through advisory resolution links;
  never automatically merge them or count them as independent confirmation of their upstream
  source.

## Rights quarantine

The checked [PeeringDB assessment](peeringdb.md) found exactly 1,548 Scrutica evidence rows whose
`data_source` is PeeringDB. All 1,548 are labeled CC BY-SA in the local release, but none records
PeeringDB permission or another upstream license basis. PeeringDB's official policy does not clearly
permit the Atlas's bulk redistribution or commercial use. Relabeling those rows would not fix the
missing authority.

The immutable Scrutica release is therefore a local-research artifact and is excluded from the
current public/open federation. As a coarse fail-closed boundary, the whole mixed-rights child—not
only the 1,548 known PeeringDB rows—remains quarantined until the reuse basis for every upstream
family is recorded and validated. The crawl, release, and crosswalk remain useful for internal
coverage and resolution research, but they are not redistributable atlas output.

## Reproducible fetch

The public MCP endpoint is unauthenticated and documents a 60-request-per-minute limit. The fetcher
uses no credentials, sends requests serially, and enforces at least 1.1 seconds between MCP request
starts (at most about 54.5 per minute). Its CLI defaults to only 50 MCP attempts per run, so a full
inventory is an intentional, resumable operation rather than an accidental long crawl.

```sh
python3 scripts/fetch_scrutica.py \
  --output saved-scrutica \
  --max-requests 50
```

On the first run, all 85 directory HTML pages are fetched before any facility request. The manifest
pins every page request to `sort=name&dir=asc&page=N` and fails closed unless it proves that
ordering contract, the pinned counts, page sizes, unique facility IDs, stable page order, and a hash
for every raw HTML page. A bundle created under the earlier default-order contract cannot be
resumed; use a new output directory. Every completed facility task stores:

- the exact `text/event-stream` bytes in `records/<facility-id>.sse`;
- the validated JSON-RPC request ID and returned facility ID;
- canonical parsed JSON in `records/<facility-id>.json`;
- byte counts, SHA-256 hashes, attempts, failures, and fetch time in `manifest.json`.

HTTP 429 responses honor `Retry-After`; other transient server failures use bounded backoff. A task
that exhausts retries remains failed until a later run explicitly passes `--retry-failed`. The
`--max-failures` circuit breaker and per-run `--max-requests` cap are recorded in the manifest.
Completed files are rehashed and reparsed on resume, and completed network requests are not repeated.

## Offline import

Import only into a new or existing Scrutica-only database:

```sh
python3 scripts/import_scrutica.py \
  --input saved-scrutica \
  --database scrutica.sqlite \
  --retrieved-at 2026-07-18T20:00:00Z
```

The importer rejects an incomplete bundle by default. `--allow-partial` examines only completed
tasks and emits an uppercase partial-coverage warning; pending or failed tasks remain unknown
coverage, not skipped rows or negative evidence. Every run also reports completed records examined,
in-scope records imported, excluded records skipped, and exact exclusion counts by type. It rejects
any target database already containing a non-Scrutica evidence family. The release builder
independently rejects a database containing both Scrutica and another source family.

Each in-scope row becomes one source-scoped `facility` with stable key
`scrutica:<facility-id>`. The evidence and release-input provenance carry the scope-policy version,
the complete allowlist, aggregate examined/imported/excluded counts, and per-type exclusions. The
adapter does not create campuses, buildings, or projects and does not merge with existing entities.
It maps only explicit `ai_training` to the AI-training workload and exact `colocation` to the
colocation operating model; labels such as `hyperscale_dc` do not imply a hyperscaler. Only the
strict status whitelist (`announced`, `permitted`, `under_construction`, `operational`, `expanding`,
and `decommissioned`) maps to canonical lifecycle states. Everything else is retained verbatim in
metadata and maps to `unknown`.

`power_capacity_mw`, `it_load_mw`, and `pue` become gross-facility MW, critical-IT MW, and PUE,
respectively. Their stage remains `unknown`; `is_estimated=false` is reported and every other case
is conservatively modeled. No annual-energy value is derived. The complete facility document,
dates, `energy_profile`, water fields, ownership/operator fields, provenance, quality flags, and raw
artifact hashes remain attached to evidence metadata.

## Isolated release

After the fetch manifest reaches `completed`, build the immutable child release directly from the
verified cache:

```sh
python3 scripts/build_scrutica_snapshot.py \
  --input saved-scrutica \
  --output-dir releases/scrutica-2026-07-18 \
  --as-of 2026-07-18 \
  --retrieved-at <timestamp-at-or-after-fetch-completion> \
  --recorded-at <same-or-later-timestamp>
```

The builder imports into a same-parent staging directory, requires the exact 4,234 examined / 4,120
retained / 114 excluded reconciliation, validates that every evidence row belongs only to the
`scrutica` source family, verifies temporal cutoffs and database invariants, and publishes by one
directory rename. It copies the exact completed fetch manifest into the release, adds the isolated
SQLite database and review map, and hash-binds every file. The child manifest declares
`review_only: true`; a federated index therefore counts these rows separately from non-review
source-scoped records. Existing or partial outputs are never repaired in place.

The completed `releases/scrutica-2026-07-18/` bundle contains 4,120 retained facility rows and
3,540 coordinate-bearing rows. Its source-scoped lifecycle arithmetic contains 159 announced, 46
under-construction, and three expansion rows; these are 208 source observations, not deduplicated
projects or unique sites. The release manifest SHA-256 is
`49846e09124e5c7daa0bef2bdece310136988339a1191cd802a8a4ea28fc42a3`.

## Dependency roots

Scrutica is the immediate publisher, while its `data_source` determines the upstream dependency root
used for independence checks: Epoch labels map to `epoch_ai`; IM3/OSM labels to `openstreetmap`;
PDB/PeeringDB labels to `peeringdb`; gridstatus labels to `gridstatus`; other labels use a stable,
lowercase normalized value. `independent_corroboration` is always false.

Recheck [Scrutica's directory](https://scrutica.com/facilities),
[methodology](https://scrutica.com/methodology), [about/license page](https://scrutica.com/about),
and [MCP documentation](https://scrutica.com/api/mcp/llms.txt) before a production refresh.
