# Virginia DEQ data-center air-permit evidence lane

This dated lane preserves the facts visible on official Virginia Department of
Environmental Quality pages while failing closed on reuse rights and Atlas
inference. It is not a publishable data-center inventory.

## Rights and access decision

The [Virginia DEQ terms page](https://www.deq.virginia.gov/news-info/about-us/terms-of-use)
shows an “All rights reserved” notice and no affirmative redistribution license
was identified. Public access is not treated as permission to reuse. Therefore:

- `publication_eligible` is false for the assessment, every issued-permit row,
  the application record, and every linked document.
- Raw HTML, permit PDFs, and application documents are not included.
- The browser-readable pages were reduced to normalized, local-review facts.
- Direct unattended HTTP probes returned 403. Their access-denied response
  sizes and hashes are checkpoints only; the bodies are not source content and
  are not retained.
- No linked permit or application PDF was parsed.

This is a conservative provenance decision, not legal advice. Reassessment
requires an affirmative license or written permission that covers the intended
storage, redistribution, and product use.

## Frozen source snapshot

The issued-permit source is the official [Issued Air Permits for Data Centers](https://www.deq.virginia.gov/news-info/shortcuts/permits/air/issued-air-permits-for-data-centers)
page with the observed heading `Issued Air Permits for Data Centers as of
7/13/2026`.

The frozen table contains 198 record-level permit actions. The page widget also
reported 194 rows. Both observations are retained because the discrepancy could
not be safely reconciled from the official page. It is not silently normalized.

Status counts are intentionally lane-specific:

| Evidence status | Rows |
| --- | ---: |
| Issued air permit | 198 |
| Application under review | 1 |
| Construction verified | 0 |
| Publication eligible | 0 |

The issued-permit program counts are 190 Article 6 mNSR, six Article 5 SOP, and
two Article 1 Title V rows. Regional-office counts are 171 Northern, 22
Piedmont, two Southwest, two Valley, and one Tidewater.

The table contains 197 resolved row-level permit-document URLs representing 196
distinct URLs, plus one unresolved official link. The unresolved row is
`74063-5`. Rows `74331-1` and `74333-1` point to the same exact official URL.
The source date `03/26-2026` on `74333-1` remains a source-format anomaly with no
inferred ISO date. The source spelling `Article 6 mNSR` on `74335-1` is retained
alongside its normalized program label.

Eight registration numbers appear in more than one permit action: `21527`,
`71804`, `73200`, `73370`, `73643`, `73670`, `73717`, and `73977`. These are
possible-duplicate review groups only. Records are not merged, and the row count
is not presented as a unique physical-site count.

## Separate under-review application lane

The official [Project Raspberry page](https://www.deq.virginia.gov/news-info/shortcuts/topics-of-interest/google-s-project-raspberry)
describes Minor NSR request `21819-1` as currently under review. It is kept
separate from issued permits. The record preserves the applicant, associated
company, location text, receipt date, program, regional office, and eight exact
official document links without retaining or parsing those documents.

The same official project-page summary source-types these proposed emergency
generation facts:

| Proposed equipment group | Count | Electrical nameplate | Engine power |
| --- | ---: | ---: | ---: |
| Caterpillar 3516E critical emergency generators | 114 | = 2,750 kWe each | = 4,043 bhp each |
| Caterpillar 3512C critical emergency generators | 6 | = 1,750 kWe each | = 2,584 bhp each |
| Emergency diesel fire pumps | 2 | Not stated | < 750 bhp each |
| Booster-pump emergency generator | 1 | = 1,000 kWe | < 1,500 bhp |
| HUB emergency generator | 1 | = 1,000 kWe | = 1,500 bhp |
| Site-entrance-booth emergency generator | 1 | < 560 kWe | < 750 bhp |

The source also states a proposed combined 3,617-hour limit per rolling 12
months for the first 120 critical generator sets and a proposed individual
100-hour limit for each remaining emergency generator and fire pump. These are
source-typed equipment and operating-limit facts. The lane deliberately does
not sum or translate them into facility MW, IT load, grid demand, annual energy,
PUE, workload, data-center type, facility status, or unique sites.

## Determinism and validation

The bundle is
`source_assessments/virginia-deq-air-permits-2026-07-13-v1/`. Its pinned hashes
are:

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `assessment.json` | 7,127 | `e51aa4ab07d822d995dd030f725f01ca75fe40bbb378d8b9adc6b960ca69fe39` |
| `issued_permits.json` | 320,823 | `c15c349c1e4110d769c09d44928c1aa7b38b1d70d18cd4bf3d54b0040a11b493` |
| `applications.json` | 11,698 | `ff4caf6b01fe89223eb9f093bcbc1cd4bbb78a4ca4e80bc0f9070439fd426d21` |
| `manifest.json` | 623 | `61ca0146274a3046dc036ba83e54bde36b0b38688e25bf27c2baff5c3dacede8` |

Validate offline from the repository root:

```bash
python3 datacenter_atlas/scripts/validate_virginia_deq_air_permits.py
```

Rebuild an exact byte-for-byte copy without network access:

```bash
python3 datacenter_atlas/scripts/build_virginia_deq_air_permits.py \
  --output-dir /absolute/new/output/path
```

The validator enforces canonical JSON, the exact source-document hashes,
manifest and sidecar hashes, official Virginia DEQ HTTPS URLs, exact row order
and keys, the count/link/date anomalies, unmerged duplicate-review groups,
separation of issued and under-review records, and null Atlas lifecycle,
capacity, energy, PUE, workload, and unique-site fields. It performs zero
network requests.

## Limitations

- This is Virginia air-permit evidence, not global coverage and not a Virginia
  completeness claim.
- An issued air permit does not prove construction, operation, ownership,
  facility type, or electrical service.
- A registration number is not proven to identify one unique physical site.
- Site names and locality labels are source facts, not resolved Atlas entities.
- Linked-document contents and page-number provenance are absent because the
  rights and access gate prevented PDF parsing.
- The Project Raspberry equipment metrics are applicant-proposed facts from the
  official project-page summary, not facility load or consumption measurements.
