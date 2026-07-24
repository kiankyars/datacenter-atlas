# South Korea EIASS/NIER source lane

The Korean Public Data Portal currently documents two NIER machine-readable
project-list operations relevant to environmental-assessment discovery:

- `getDscssBsnsListInfoInqire` covers environmental-impact-assessment
  discussion-status projects; and
- `getBsnsStrtgySmallScaleDscssListInfoInqire` covers prior, strategic, and
  small-scale assessment discussion-status projects.

Both return XML. Both require a Public Data Portal `serviceKey` and `pageNo`;
the second also requires `numOfRows`. Responses expose `pageNo`, `numOfRows`,
and `totalCount`. Each list accepts `searchText`, described only as a project or
business-name search. The documentation does not define exact-phrase versus
substring behavior, a default or maximum page size, stable ordering, or a
snapshot/as-of contract.

The resource pages mark both APIs as including third-party rights under an
attribution condition and as Public Works Type 1. The directly audited portal
policy defines Type 1 as requiring attribution while allowing commercial,
noncommercial, and derivative use. That affirmative scope is for the listed
API resources; it does not automatically extend to EIASS web pages, web-search
results, or EIA documents.
Browser-proxy review of the official EIASS copyright policy and terms found an
All Rights Reserved footer, free reuse limited to KOGL-marked works, prior
consultation for unmarked material, and restrictions on unapproved
reproduction, distribution, alteration, sale, or commercial use. Those pages
were not directly requested after the EIASS robots origins failed, and the
proxy's origin-request count is unknown.

The services are public and free but not anonymously callable. The portal
labels development and operating review as automatic approval and lists
development traffic as 10,000 without stating the period. No service key was
provided or used in this lane.

The official 7 May 2025 notice says that 22 former KEI EIASS OpenAPI services
were discontinued after EIASS transferred to NIER and identifies identical
NIER replacements. The mapping attachment is currently labelled as recovering;
it was not requested, so this lane does not claim that its contents were
verified.

The assessment is frozen at zero rows because:

- `https://apis.data.go.kr/robots.txt` returned HTTP 500 rather than a usable
  policy;
- both direct EIASS robots attempts failed before an HTTP response;
- no service key was supplied;
- stable sorting, snapshot semantics, page-size bounds, and search matching
  behavior are undocumented; and
- EIASS administrative records do not cover every Korean planning, building,
  grid, or physical-construction event.

Neither Korean literal, `데이터센터` or `데이터 센터`, was submitted. English
variants `data center` and `data centre` remained disabled because the gates
did not clear. No API operation, web search, export, result detail, attachment,
document, or geometry request was made.

The controlled audit used 10 direct-origin attempts under a cap of 40, with
request starts at least 3 seconds apart. Seven attempts returned HTTP
responses and three failed at the network layer. Browser-proxy research is
recorded separately with unknown origin-request count and excluded from the
exact direct-request arithmetic.

An EIA discussion-status row is review-only administrative evidence. It is not
evidence that a physical data centre exists or that construction started,
completed, or entered operation. Data-centre type, IT capacity, gross power,
PUE, and annual energy remain null, and the lane cannot feed the construction
master, map, or current-coverage ledger.

Validate the frozen release offline from this directory:

```bash
python3 scripts/validate_south_korea_eiass_nier.py
```
