# England Planning Data assessment

This lane publishes a frozen, conservative set of planning observations from
the official MHCLG [Planning application dataset](https://www.planning.data.gov.uk/dataset/planning-application).
It is not a facility inventory and does not claim complete England coverage.
The source page itself says the dataset is incomplete and not yet ready for
use, and that its MHCLG-created data will be replaced by authoritative sources
when available.

## Snapshot and rights

The release `source_assessments/england-planning-data-2026-07-18-v1/` was
retrieved at `2026-07-18T23:50:50Z` using eight bounded HTTPS requests to
official first-party endpoints:

1. the Planning Data bulk CSV;
2. the Planning Data dataset page;
3. the Planning Data dataset JSON metadata;
4. the National Archives OGL v3 legal code; and
5. four Planning Data provider-entity JSON records.

The CSV object is exactly 44,513,805 bytes, SHA-256
`c09847e03d0da35f41e4f3b9a0c9e815ddeb9c0460d35c4b75712651056a75aa`,
ETag `"29688ef098fc662123b1cfe5baab0db3-6"`, S3 version
`hHnEr9InrX7sadW2XR1YnbplPITGhhog`, and Last-Modified
`Tue, 09 Sep 2025 03:36:15 GMT`. The page says the collector last ran and new
data was last found on 2025-09-17. Both dates are preserved without treating
them as equivalent.

The dataset metadata and page state Open Government Licence v3.0 and the
specified attribution `© Crown copyright and database right 2026`. The frozen
National Archives legal code confirms reuse and adaptation, including
commercial use, subject to attribution. It also excludes personal data and
unlicensed third-party rights, prohibits implied endorsement, and supplies the
information without warranty. The builder fails closed if any pinned rights or
lineage byte changes.

## Exact row and provider inventory

The bulk snapshot has 100,627 logical data rows, 100,627 unique entity IDs, and
the exact 26-field header retained in `source-inventory.json`. Geometry is
available as a `point` string on 98,696 rows; 1,931 have no geometry in any of
the `point`, `geometry`, or `geojson` fields. No missing geometry is fabricated.

The page reports an aggregate of six data providers, but the bulk bytes contain
only four `organisation-entity` values:

| Provider entity | Official name | Bulk rows |
| ---: | --- | ---: |
| 26 | Adur District Council | 7,585 |
| 90 | London Borough of Camden | 77,499 |
| 109 | Doncaster Metropolitan Borough Council | 1,914 |
| 382 | Worthing Borough Council | 13,629 |

The page does not identify the other two counted providers or explain whether
its metric counts upstream feeds, superseded providers, or something else. The
assessment records this as an unreconciled source discrepancy; it does not
invent provider identities.

This is plainly not an England-wide planning register. Only the four provider
entities above have rows in the pinned bulk file. Relevant applications can
also be missed when descriptions omit the selected vocabulary.

## Phrase selection and reviewed precision

Selection examines only the raw `description` field. It applies NFKC,
case-folding, collapsed whitespace, and ASCII alphanumeric token boundaries,
then matches the explicit phrases `data centre`, `data center`, `datacentre`,
and `data-center`. The result is four rows, all using `data centre`:

| Entity | Reference | Context assessment |
| --- | --- | --- |
| 10000009092 | AWDM/0934/19 | Proposed construction of two data-centre cabins |
| 10000057188 | 2022/3535/P | Context-only: the existing data centre is excluded from the proposed temporary change of use |
| 10000088724 | 2013/2585/P | Wider redevelopment includes a relocated data centre |
| 10000090380 | 2020/2009/L | Opening between an existing data centre and lift motor room |

The context-only row is intentionally retained because it is a reproducible
explicit-phrase planning observation, but it is explicitly labeled and cannot
be promoted to construction evidence. Thus the four-row exact-match audit is
three direct-scope planning mentions plus one context-only exclusion, not four
construction leads or four data-centre leads.

Optional terms were measured incrementally outside the explicit set:

| Optional phrase | Incremental rows | Decision |
| --- | ---: | --- |
| `data hall` | 0 | No candidates to add |
| `server room` | 3 | Excluded after review |
| `data processing` | 0 | No candidates to add |

The three `server room` rows concern two drainage-consent records for a small
internal room and one basement partition/kitchen reconfiguration. They do not
establish a data centre. Their raw descriptions, statuses, dates, addresses,
geometry, row numbers, and hashes remain in `phrase-review.json`, making the
exclusion reproducible. No optional row is added.

## Evidence boundary

Every output row is a `planning_application_observation`, `review_only: true`,
and `auto_merge: false`. Every one of the 26 source strings is preserved in
`source_attributes`, with convenience copies of the raw description, status,
date, and geometry fields. The row hash is SHA-256 of canonical JSON containing
all 26 ordered raw source fields. The exact CSV file hash and logical row number
are also attached.

A planning application can be refused, withdrawn, amended, duplicated,
implemented, or never implemented. Its application status and decision do not
establish facility identity, unique site, construction, operation, lifecycle,
data-centre type, capacity, power, annual energy consumption, PUE, ownership,
operator, workload, or completion. Every such field remains false or null, and
promotion is forbidden without independent evidence and manual review.

## Reproduction and validation

The bundle retains all eight official raw inputs byte-for-byte, plus canonical
assessment, definition, schema, inventory, phrase review, JSONL, CSV,
attribution, and README artifacts. The manifest SHA-256 is
`774c51894a2a46cbb10459cc1ebd777059c5bdab425599bfc48b6dd9d248676c`.
Core derived hashes are:

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `assessment.json` | 6,758 | `4cedd446a017289a6aef6387757e4c18f45177d565621d9944929025bb02beb6` |
| `source-inventory.json` | 5,012 | `c42e9fc6d2c2be92ae1d42d54662421e9a986e4b39aaf92f66ffb5c0ae5630e8` |
| `phrase-review.json` | 3,754 | `4249f3413e5073ea4d2f446825c25edddb46f406067c406ace39c2ae09bba7e3` |
| `observations.jsonl` | 13,927 | `7859efa54933beffbcb69240aab92c28ea819fd72f8baa286b1fc82487334ca5` |
| `observations.csv` | 4,553 | `ad52fbc1afa7d8b4b273989798173565f5a550daef2c295556ed33c90ed94a2e` |

Validate the release with zero network requests:

```sh
python3 scripts/validate_england_planning_data.py
```

Fetch a new copy only when intentionally assessing the same pinned snapshot:

```sh
python3 scripts/fetch_build_england_planning_data.py \
  --output /absolute/new/release/path
```

The builder refuses an existing output. The validator checks the closed file
set, canonical JSON, manifest and raw hashes, exact official URLs, OGL gate,
provider identities, CSV schema/object metadata, row and phrase counts, raw
field hashes, review-only boundaries, and deterministic offline re-derivation.
A changed upstream snapshot requires a new release ID and definition.
