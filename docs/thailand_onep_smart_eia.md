# Thailand ONEP Smart EIA approved-report lane

## Outcome

The 18 July 2026 assessment is a frozen, metadata-only source lane. ONEP's
official CKAN record passed the narrow rights/access gate, but the catalog-linked
JSON resource failed the completeness gate. The single resource response
declared 13,793 records over 138 pages and returned only page 1 with 94 records.
No pagination was attempted, no source row was retained, and no data-centre lead
was promoted.

This lane covers only environmental-assessment reports listed by ONEP as
approved. It does not cover all Thai projects, sites, planning decisions,
construction permits, construction starts, completions, or operating data
centres.

## Official surfaces and rights boundary

- Public report list: <https://eia.onep.go.th/site/eia>
- ONEP CKAN dataset: <https://onep.gdcatalog.go.th/en/dataset/database1>
- CKAN `package_show`: <https://onep.gdcatalog.go.th/api/3/action/package_show?id=database1>
- Catalog-linked JSON resource: <https://eia.onep.go.th/services/web/open-api/eia-list>
- Privacy policy: <https://eia.onep.go.th/site/policy>
- Robots URL: <https://eia.onep.go.th/robots.txt>

The CKAN record's exact licence title and ID are `Creative Commons
Attributions`. The record supplies no licence version and no licence URL. The
release preserves that literal label without mapping it to a particular
Creative Commons version. ONEP is attributed. The label is not extended to
linked PDFs, spreadsheets, reports, or other document content. No document was
requested. The privacy page is not treated as a dataset licence, and the robots
URL's HTTP 404 is not treated as permission.

## Controlled request ledger

The audit made exactly four HTTP GET requests, with a 60-second timeout, at most
three redirects, a 100 MiB response-body ceiling, no retries, and a 25,000-record
ceiling:

| Request | Status | Redirects | Transfer bytes | Captured body bytes | Captured-body SHA-256 |
|---|---:|---:|---:|---:|---|
| CKAN `package_show` | 200 | 0 | 13,432 | 13,432 | `d27e73ab44c877edb891a2f5a3d888e7d6967c9728c48f38bf7e379a251f7144` |
| Privacy policy | 200 | 0 | 15,488 | 86,108 | `4cd20c37433239b665412b9b5a5170d6827479f6ef48b1231e18834c36d58030` |
| Robots URL | 404 | 0 | 24,877 | 24,877 | `d28aad79dccd2af221a407ef60d246438e9a346240c5af8c5e99867b59c7bf9c` |
| JSON resource snapshot | 200 | 0 | 60,783 | 60,783 | `775e24d2e31bb2f192129422cf1d2aac498c61cf1d3d13570ee10e418a5abe36` |

Curl content decoding was enabled. The privacy response was gzip-encoded, so
its transfer size differs from the exact decoded body bytes that were hashed.
The other three responses were not content-encoded.

The canonical JSON SHA-256 values are
`b7b571fa0a02c7bc96f29c0686c2f14f22d0e5c5a9ac4fe2f9cd49f168ca7b9d`
for the CKAN envelope and
`5926ac673c653de85fdc85cf0befdf6bc1dee358b816025c7b2fefac9c45d345`
for the resource envelope. Canonical JSONL for the 94 returned rows hashes to
`1d74c5661304d3a07f4197a7c3c4351dfe874b8d7d209d5db131104038b56ea4`.
Only the hashes and diagnostics are released; the volatile raw bodies and the
partial source rows are not.

No UI crawling, pagination, detail pages, PDFs, Excel files, report documents,
login, registration, or CAPTCHA activity occurred. Release building and
validation perform zero network requests.

## Completeness and freshness gates

The returned JSON had the exact top-level fields `dataList`, `totalCount`,
`currentPage`, and `totalPage`. Each of the 94 rows had the ten expected text
fields: `year`, `name`, `owner`, `category`, `province`, `zone`, `approve_date`,
`approve_number`, `code`, and `reporter`. The returned page had 94 distinct
`code` values and no conflicting key collision.

The page is incomplete because `currentPage=1`, `totalPage=138`, and
`totalCount=13793` while `dataList` has only 94 rows. Its Buddhist Era year was
2569. Parsed approval dates ranged from 2 March 2026 through 30 December 2026;
three dates were later than the 18 July assessment date. The assessment therefore
does not use the page to claim current coverage or freshness. The CKAN metadata's
1992 start-year statement, monthly update-frequency label, 1 July 2024 dataset
date, and 30 January 2024 resource date remain catalog claims rather than
observed complete-snapshot boundaries.

Audit mode records the future-date count without retaining rows. Any otherwise
complete future snapshot containing even one approval date after its assessment
date fails before candidate or review-shard derivation.

## Matching and identity contract

Text normalization is Unicode NFKC, casefolding, and whitespace collapse. Only
the project `name` field is matched. The high-precision direct terms are:

- `ดาต้าเซ็นเตอร์`
- `ดาต้า เซ็นเตอร์`
- `ศูนย์ข้อมูลคอมพิวเตอร์`
- `ศูนย์ประมวลผลข้อมูล`
- `data center`
- `data centre`
- `internet data center`
- `internet data centre`
- ASCII-token-bounded `IDC`

Generic `ศูนย์ข้อมูล` is accepted only when the same normalized name also
contains `คอมพิวเตอร์`, `คลาวด์`, `อินเทอร์เน็ต`, or `เซิร์ฟเวอร์`. The partial
page's diagnostic match count was zero; this is not a global result count.

A future complete snapshot is deduplicated by exact ONEP `code`. Exact duplicate
rows collapse; conflicting rows with the same code fail closed. Observation IDs
are deterministic UUIDv5 values derived from the official resource namespace and
exact code. The closed candidate union is capped at 500. Local review shards are
exact match term × Gregorian approval year × province and capped at 250. Inputs
must be explicitly split or rejected rather than truncated.

## Semantic boundary

A future retained match would be a Tier-C ONEP-approved environmental-assessment
report observation in the IEE/EIA/EHIA catalog family. It would not establish a
unique atlas project or site. Report approval is not a construction, completion,
commissioning, or operating milestone. The returned schema has no documented
project-status field, so lifecycle remains null. `owner` is retained only as a
raw source field and is not treated as operator.

Coordinates, data-centre type, gross facility power, IT capacity, PUE, annual
energy consumption, and every physical lifecycle field remain null. The lane has
no automatic construction-master, map, or current-coverage-ledger import.

## Validation

The release is at
`source_assessments/thailand-onep-smart-eia-approved-reports-data-centre-snapshot-audit-2026-07-18-v1`.
The checked-in definition is at
`sources/thailand-onep-smart-eia-approved-reports-data-centre-snapshot-audit-2026-07-18-v1.json`.

Run the offline validator from `datacenter_atlas/`:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate_thailand_onep_smart_eia.py
```
