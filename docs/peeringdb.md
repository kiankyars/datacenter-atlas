# PeeringDB source assessment

Assessment date: 2026-07-18. Decision: **blocked pending written permission**.

No bulk PeeringDB facility cache or Atlas release was created. The immutable assessment bundle at
`source_assessments/peeringdb-2026-07-18-v1/` retains only retrieval metadata, byte counts, hashes,
field names, and the resulting source-governance decision. It retains no PeeringDB facility record
values or fetched source documents.

## Access and scope

PeeringDB's [API specification](https://docs.peeringdb.com/api_specs/) permits guest reads without
authentication, subject to lower query limits. A one-record anonymous probe of
`GET https://www.peeringdb.com/api/fac?page=1&per_page=1` returned HTTP 200 and pagination metadata
reporting 5,857 facility records at `2026-07-18T21:10:31Z`. The raw response was hashed and then
discarded; no field values were retained.

The deployed OpenAPI schema calls `fac` a “Facility (Datacenter)”. PeeringDB's
[facility operator guide](https://docs.peeringdb.com/howto/get-started-facility/) and
[approval guidelines](https://docs.peeringdb.com/committee/admin/approval-guidelines/) make the
scope narrower than an all-data-centre census: facilities are user-maintained physical locations
for network or Internet-exchange interconnection. This is a useful colocation/interconnection
registry, not evidence that every operating, planned, or under-construction data centre is present.

The structured facility response provides identifiers, names, organization and campus references,
addresses, nullable coordinates, network/exchange/carrier counts, administrative timestamps, and
limited power/resilience descriptors. `available_voltage_services` contains voltage categories;
it is not MW capacity or energy consumption. The record `status` is an administrative state such
as `ok`, `pending`, or `deleted`; it is not construction lifecycle. The current schema has no
structured gross MW, IT MW, annual energy, PUE, commissioning date, construction status, or
workload type. Free-text notes must not be promoted into those claims without separate evidence.

## Rights boundary

PeeringDB's live [Acceptable Use Policy](https://www.peeringdb.com/aup) is marked “All Rights
Reserved”. It names Internet research and analysis within Internet-operational uses, but it also
requires approval outside approved purposes, excludes commercial applications, and says bulk data
may not be passed to another person or organization without PeeringDB approval. No affirmative
permission covering this Atlas's intended bulk storage, derivative use, redistribution, or
commercial use was found in the official sources.

The conservative rule is therefore:

- do not bulk-fetch or build a direct PeeringDB cache or release;
- do not publish PeeringDB-derived rows;
- obtain written permission that expressly covers storage, retrieval volume, derivatives,
  redistribution, attribution, and commercial use if applicable;
- record that permission in a new versioned assessment before any direct fetch;
- keep any eventual direct lane review-only and source-isolated; and
- never count direct PeeringDB and Scrutica's PeeringDB-derived rows as independent evidence.

This is a source-governance decision, not legal advice. Relabeling rows does not create permission.

## Scrutica upstream-rights conflict

An offline, read-only audit of the already immutable
`releases/scrutica-2026-07-18/` bundle verified its manifest hash
`49846e09124e5c7daa0bef2bdece310136988339a1191cd802a8a4ea28fc42a3` and found:

| Finding | Rows |
| --- | ---: |
| Scrutica evidence rows | 4,120 |
| Evidence with `metadata.data_source = peeringdb` | 1,548 |
| Source-created entities backed by those rows | 1,548 |
| Those evidence rows labeled `CC-BY-SA-4.0` | 1,548 |
| Rows recording PeeringDB permission or an upstream license basis | 0 |

All 1,548 affected evidence rows carry the attribution “Scrutica data, licensed under CC BY-SA
4.0”, and the release-level `ATTRIBUTION.txt` says the same. Scrutica's public
[facility directory](https://scrutica.com/facilities) independently reports 1,548 PeeringDB rows
while displaying a CC BY-SA footer. Neither the local release nor the reviewed public page records
evidence that PeeringDB authorized that sublicense or bulk redistribution. Scrutica's blanket
license label therefore cannot be treated as proof that the upstream PeeringDB rights were cleared.

The fail-closed publication rule is to quarantine or exclude the 1,548 PeeringDB-derived evidence
rows, their 1,548 source-created facilities, 1,548 snapshots, 1,548 lifecycle observations, and
1,548 operating-model observations from redistributed artifacts. They have no associated capacity
or workload observations in this release. The immutable release is not modified in place.
Independently sourced replacement facts can be published only from their independent evidence.

## Offline validation

The validator performs no network requests. It validates the exact assessment file set and hashes,
then opens the Scrutica SQLite database with `mode=ro`, `immutable=1`, and `query_only=on` and
recomputes the affected rows:

```sh
python3 scripts/validate_peeringdb_assessment.py
```

Use `--skip-scrutica-audit` only when the immutable Scrutica release is intentionally unavailable.
