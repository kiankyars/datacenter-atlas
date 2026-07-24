# Denmark Plandata.dk local-plan source assessment

The frozen release is
[`denmark-plandata-local-plan-data-centre-search-2026-07-19-v1`](../source_assessments/denmark-plandata-local-plan-data-centre-search-2026-07-19-v1/).
It is a bounded discovery assessment of official local-plan features, not a
national inventory of data centres and not an Atlas construction import.

## Closed search

The source field is exactly `plannavn`. The lane applies a case-insensitive OGC
`PropertyIsLike` contains filter for nine predeclared literals:

`datacenter`, `datacentre`, `datacentret`, `data center`, `data centre`,
`servercenter`, `servercentre`, `servercentret`, and `serverhal`.

Each literal is run against exactly three WFS 2.0 layers:

- `pdk:theme_pdk_lokalplan_forslag` (`status=F`, proposal)
- `pdk:theme_pdk_lokalplan_vedtaget` (`status=V`, adopted)
- `pdk:theme_pdk_lokalplan_aflyst` (`status=A`, cancelled)

That is a closed 27-query plan. The exact generated URLs are in
`query-plan.json`. Hit counts use `resultType=hits`. Positive queries use a
stable `id A` sort, 100-feature pages, at most three pages per query, and no
more than 8,100 features or 115 requests globally. The clean frozen capture
enforced a minimum five-second interval. A count or page mismatch, redirect,
unexpected HTML outside the pinned robots 404, schema change, source error,
repeated page feature, or short non-final page fails closed.

Only two queries were positive:

| Query | Layer | Literal | Hits | Pages | Retrieved |
| --- | --- | --- | ---: | ---: | ---: |
| `q10` | adopted | `datacenter` | 3 | 1 | 3 |
| `q11` | adopted | `datacentre` | 2 | 1 | 2 |

The other 25 query counts were zero. The five retrieved memberships deduplicate
to five status-layer local-plan observations, all from the adopted layer:

- `Datacenter ved Sæby Varmeværk`
- `Datacenter og rekreativt område`
- `Erhvervsområde til datacentre`
- `Udvidelse af datacenter i Tietgenbyen`
- `Datacentre i Høje Taastrup`

These exact-name results do not establish Danish recall beyond the field,
layers, literals, and capture time. Attached plan-document text was not searched.

## Control evidence and rights boundary

The clean capture made 35 controlled GETs: six controls, 27 hit-count requests,
and two result pages. It revalidated:

- the Datavejviser JSON-LD record for `Local plan - PlanDK`, with exact licence
  URI `http://publications.europa.eu/resource/authority/licence/CC_BY_4_0` on
  the dataset and all four referenced distributions;
- `Plan- og Landdistriktsstyrelsen` as an official publisher;
- the WFS 2.0 capabilities document, all three selected layers, JSON output,
  `ImplementsResultPaging=TRUE`, and the documented `CountDefault=1000000`;
- all three complete `DescribeFeatureType` schemas, including the exact
  `plannavn`, `status`, `megawatt`, planning-maxima, and geometry field types;
- an HTTP 404 HTML response at the WFS host's robots path.

The documented default count is a source diagnostic, not a chosen page size or
permission to make an unbounded request. A missing robots file is not permission.
The catalogue licence is preserved with Plandata.dk / Plan- og
Landdistriktsstyrelsen attribution. This assessment uses the alternative
official WFS endpoint identified by Plandata.dk's own WFS guide, makes no legal
conclusion, and does not extend the catalogue licence to linked plan documents.

Every final-capture request URL, request/completion timestamp, response `Date`,
HTTP status, content type, redirect count, byte count, and SHA-256 is stored in
`capture-metadata.json`. Raw response bodies are not retained. The six control
response SHA-256 values are:

| Request | Status | Bytes | SHA-256 |
| --- | ---: | ---: | --- |
| licence JSON-LD | 200 | 13,759 | `92e5d3e2072ada48b00520044242224aed72e68b3776a893b705b38fa7b91707` |
| robots | 404 | 153 | `533a1ca5d6595793725bca7641d9461a0f00dd1732dded3e4281196f5dd21736` |
| WFS capabilities | 200 | 222,295 | `4f8e5457feaf6e98541a803efa2225e1311644aa2feb032e86292bc6672d2f2f` |
| proposal schema | 200 | 34,120 | `c124e8ec21dc4f786b36b5ef5d8a52222960376f94419145b4168ad52e1ad7ef` |
| adopted schema | 200 | 34,326 | `8469abff4157ee238c315c7f4dba06821916e9959205e1b4142ecc9bb0649fca` |
| cancelled schema | 200 | 34,221 | `f209e5903239ea80eba58bddaa93076e0bb7203a6d63aa7c34a451e9055a757d` |

## Full task request accounting

The final capture is not the only direct local traffic made while implementing
the lane. The task made 67 direct GETs to official endpoints, below the
predeclared 115-request hard cap:

- 35 final, hash-bound capture GETs;
- 12 discarded implementation preflight GETs;
- 17 GETs in an aborted capture attempt;
- 3 discarded one-feature status-code diagnostics.

The first attempt stopped on its seventeenth request: six controls, q01-q09 hit
counts, q10's three-hit count, and q10 page 1. The page returned HTTP 200 JSON
with three features, but the parser expected human label `Vedtaget`; the source
used exact WFS code `V`. No artifact was written. Its response bodies and
per-request metadata were discarded and are not coverage evidence. A clean
restart pinned source codes `F`, `V`, and `A`. The 12 preflights and three status
diagnostics were also discarded. Thus 35 + 32 = 67 direct local GETs. The
five-second pacing claim applies only to the clean 35-request capture; no pacing
claim is made for the 32 discarded requests. Browser/search tooling is excluded
because it may be cached or proxied and exposes no reliable origin-request count.

## Semantic boundary

A proposal, adoption, or effective date is a planning fact, not construction,
completion, commissioning, operation, or a physical facility status. A
cancelled-layer match would be negative planning evidence. Planning polygons
are plan areas, not facility footprints or facility coordinates.

The WFS schema includes planning maxima and a `megawatt` field. This first pass
does not retrieve either. A maximum is not an observed actual, and an untyped
megawatt value is neither facility capacity nor energy consumption without an
official definition of its scope. Atlas identity, operator, data-centre type,
gross facility power, IT MW, PUE, annual energy, workload, physical status, and
unique physical-site count all remain unknown.

No detail page, linked document, or PDF was requested. The five observations
are review-only source units. Construction-master, construction-map, and
current-coverage-ledger imports are all false. The release is outside current
construction master/map v10 and current-coverage ledger v6 and
does not change any current Atlas count.

## Validation

The manifest SHA-256 is
`793f95d04afae18898280c54e8726cf9c5fdedef8d914c06764e5e186df78880`.
Validate without network access:

```bash
python3 scripts/validate_denmark_plandata_local_plans.py
```
