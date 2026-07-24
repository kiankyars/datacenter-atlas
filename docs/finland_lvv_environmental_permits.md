# Finland national environmental-permit discovery

## Decision

The official machine-accessible source is Lupa- ja valvontavirasto's (LVV)
[Ympäristöasioiden tietopalvelu](https://ytietopalvelu.lvv.fi/). Its
[OpenAPI contract](https://ytietopalvelu.lvv.fi/swagger/v1/swagger.json)
documents an unauthenticated `POST /api/v1/cases/search` returning permit-case
records. A synthetic guaranteed-no-match request confirmed machine access
without retrieving source results.

This lane stops before result capture. LVV's official
[open-data page](https://lvv.fi/yhteystiedot/avoin-data) says it collects the
links to LVV's open-data contents and assigns CC BY 4.0 to LVV-produced open
data. During the 2026-07-18 local-date audit, that catalogue listed alcohol
register data and health-sector statistics, but not the environmental-permit
service. The public UI and unauthenticated API establish access, not an
affirmative right to retain and redistribute search-result metadata. The
release makes no legal conclusion; it requires source-specific clarification
before capture.

## Robots and access evidence

- `https://ytietopalvelu.lvv.fi/robots.txt` returned HTTP 404. No robots rule
  was published on the API host.
- `https://lvv.fi/robots.txt` returned HTTP 200, listed a five-second crawl
  delay, and disallowed `/search/`, `/haku/`, and `/sok/` on the main LVV host.
- `https://www.ymparisto.fi/robots.txt` returned HTTP 200 and disallowed
  `/search/` and `/index.php/search/`. The national YVA landing links to the
  locale-prefixed canonical route `/fi/search`, which is not an exact path
  prefix match for those two listed rules. That observation is not treated as
  reuse permission.
- The current `ytietopalvelu.lvv.fi` certificate validated during the audit.
  The legacy `ylupa.avi.fi` certificate had expired and the legacy URL redirected
  to the current service, so the legacy host is not a capture endpoint.

Response bodies were used transiently for the audit and are not published.
The frozen inventory records URL, method, HTTP status, content type, byte count,
response date, and SHA-256 for eight controlled audit requests. It records zero
result-bearing search requests.

## Closed query contract

The predeclared date window is 2016-01-01 00:00:00 UTC through 2026-07-18
23:59:59 UTC, inclusive. The exact literals are:

- `datakeskus`
- `datakeskukset`
- `data center`
- `data centre`

Each literal has two API variants: case-created date and latest-document-
published date. The English variants are supported by the OpenAPI `query`
string and the UI's language-neutral substring-search description. If rights
are later clarified, the backend result must still pass a Unicode-casefolded
exact-literal postfilter.

The future retrieval contract uses 25 rows per request, at most 40 pages per
variant, at most 320 result-bearing requests total, and at least five seconds
between requests. Every response must be hash-bound. An error, page ceiling, or
request ceiling stops the run and leaves completeness counts null.

The eight query variants would be unioned only by exact `CaseResponse.id`.
There is no automatic applicant/entity, project, or site merge. Every case in a
completed union must be classified as direct data-centre project,
ancillary/context, or excluded. No partial union is publishable as complete.

## Unit and inference boundaries

The API search unit is a permit-case search record. It is not a document
publication, atlas project, or physical site. Because search did not run, all
of these source counts remain null:

- result count;
- permit/license case count;
- document-publication count;
- project count;
- site count;
- classification counts; and
- source metric-statement count.

Exact retained counts are zero for permit-case rows, document rows,
classification rows, and metric rows.

LVV case stages such as initiated, informed, finalized, or transferred are
administrative process statuses. They do not establish construction start,
completion, or operation. No physical lifecycle, data-centre type, IT capacity,
gross facility power, backup generation capacity, PUE, or annual energy value
is inferred.

Applicant fields can contain natural-person data, and case documents can
contain contact or other personal data. This release retains none of them. It
contains no source titles, descriptions, attachments, geometry, or raw API
responses.

## Downstream contract and validation

This metadata-only assessment has no positive import contract for the
construction master, map, or current-coverage ledger. It must not be imported
into any of them.

The release directory is mode `0555`; every file is mode `0444`. Validate the
bundle and reproduce its derived files without network access:

```bash
cd datacenter_atlas
python3 scripts/validate_finland_lvv_environmental_permits.py
python3 -m unittest tests.test_finland_lvv_environmental_permits
python3 scripts/build_finland_lvv_environmental_permits.py \
  --output /tmp/finland-lvv-release \
  --definition /tmp/finland-lvv-definition.json
```
