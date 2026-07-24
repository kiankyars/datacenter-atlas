# Cleanview data-centers API

Cleanview documents a curated United States data-center project API with useful project labels,
locations, status, power, land, building-area, investment, and source-link fields. It is not an
anonymous or openly licensed Atlas source. The immutable assessment is
`source_assessments/cleanview-2026-07-18-v1/`; it contains only official retrieval metadata and a
derived schema contract, with no API response records or example project values.
The manifest SHA-256 is
`e56e5229c3b39929f22152dec9db8201cd3a9a0e12f28e463e3eb22932ccb5f6`;
the assessment and schema SHA-256 values are
`60089505dd662ab186ac11e5b419e18a0023ddf6426aeacb26fa99558f1e3129` and
`e3f8a8aca0f70afcffedc56f18ca0dc7cbdfb824b195a0e70d1914b6219cb324`.

## Access and licensing

The [data-centers endpoint documentation](https://docs.cleanview.co/api-reference/endpoint/data-centers)
and [OpenAPI specification](https://docs.cleanview.co/api-reference/openapi.json) require an
`x-api-key`. The [authentication guide](https://docs.cleanview.co/authentication) says keys are
manually provisioned during the beta after Cleanview reviews whether the intended use is internal
or a product integration.

The endpoint has no filters or pagination. A successful call returns every audit-approved record
in one response, documented as 500 KB or more. There is therefore no bounded one-row or metadata
probe. No API key was used and no data-endpoint request was made.

Cleanview's [pricing page](https://cleanview.co/pricing) advertises unlimited downloads and
monthly updates for Pro, phrased as use in a customer's own tools. API access and a “License for
product integration” are advertised separately under Custom. The page does not expressly grant
commercial public redistribution, derivative-database publication, sublicensing, or downstream
end-user access.

No terms or privacy page appeared at the standard `/terms`, `/terms-of-service`, `/privacy`, or
`/privacy-policy` paths or in the pinned official sitemap; all four candidate paths returned 404.
Robots allowances and the documentation host's AI content signals control crawling preferences,
not database copyright or redistribution rights. Public documentation and access alone are not a
license.

A publication reassessment therefore requires both:

- a Cleanview API key issued for the declared Atlas product-integration use; and
- a written Custom/API license expressly covering commercial use, local storage/cache,
  transformations and derivative databases, public display and redistribution, sublicensing or
  end-user access, attribution, refresh/rate limits, and retention or deletion after termination.

Any third-party articles linked by `source_1` through `source_3` remain separate rights roots; the
Atlas must not cache or republish those pages merely because Cleanview links to them.

## Documented schema

The successful response requires four top-level members: `success`, `metadata`, `customer`, and
`data`. Response metadata documents `total_count` and `generated_at`; customer metadata documents
`id` and `name`. Each project object exposes 15 properties:

- `project_name`, `developer`, `status`, and `operating_year`;
- `capacity_mw`, `land_acres`, `building_square_footage`, and `cap_ex`;
- `county`, `state`, `latitude`, and `longitude`; and
- `source_1`, `source_2`, and `source_3`.

The OpenAPI `DataCenter` schema declares no required record fields. Most properties are nullable,
and the narrative documentation additionally warns that newly announced projects commonly lack
operating year, capacity, or coordinates.

Important Atlas fields are absent: stable project/facility ID, campus-building hierarchy,
country, first-seen and record-updated timestamps, field-level source dates, status or construction
evidence, permits or groundbreaking evidence, facility type, PUE, annual energy, workload, and a
capacity metric scope distinguishing IT load from gross or utility service power.

## Coverage, freshness, and evidence

The endpoint advertises United States project records, not global coverage. The documented
`total_count: 1176` and `generated_at: 2024-12-12T10:00:00.000Z` are OpenAPI examples, not a live
count or current dataset timestamp. No data request was made, so current project count and unique
facility count remain `null`.

A project record is not necessarily one canonical facility. The API exposes no stable ID or
campus/building relationship, while its own example names can combine multiple numbered
facilities. Record total must not be presented as unique sites.

Freshness claims also differ by context: endpoint documentation says the database is continuously
updated after audit approval, general API documentation says most data is updated daily, and Pro
pricing advertises monthly updates. The endpoint schema has no per-record `last_updated`; its
`generated_at` value is response-level. There is no documented record-freshness SLA.

The advertised common statuses are `Planned`, `Operating`, and `Cancelled`, but `status` is a
nullable free-form string without an OpenAPI enum. The description also groups cancelled and
postponed projects. These editorial labels and “audit-approved” claims do not themselves verify
physical construction or operation. `operating_year` does not distinguish an actual year from a
future estimate.

Likewise, `capacity_mw` is simply documented as power capacity and may be estimated from public
announcements. It cannot be promoted to gross facility power or IT load, and peak MW cannot be
converted into annual MWh. The schema has no PUE, energy, or workload fields.

## Atlas decision and validation

The lane is `api_and_rights_blocked_metadata_only`: zero facility leads, no current record count,
no unique-site count, no capacity promotion, and no lifecycle promotion. It makes no global
completeness or parity claim.

The validator performs no network requests:

```sh
python3 scripts/validate_cleanview_assessment.py
```

It pins official documentation, OpenAPI, robots, sitemap, pricing, and legal-page discovery
responses by URL, status, byte count, and SHA-256; validates the 15-field contract; and preserves
the zero-record release boundary.
