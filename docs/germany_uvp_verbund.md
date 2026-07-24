# Germany UVP-Verbund restricted assessment

UVP-Verbund covers state and municipal environmental-assessment procedures across Germany's 16 federal states. This lane records a blocked search contract and a restricted reuse decision. It does not contain project rows.

## Search contract

The live portal client sends `GET` requests to `/freitextsuche` with the search text in `q` and the page number in `page`. Its configuration searches title, summary, and content fields. The client exposes no title-only query.

The closed query plan contains these four terms:

| Term | Exact first-page URL | Capture status |
|---|---|---|
| `Rechenzentrum` | `https://www.uvp-verbund.de/freitextsuche?q=Rechenzentrum` | HTTP 429 |
| `Rechenzentren` | `https://www.uvp-verbund.de/freitextsuche?q=Rechenzentren` | Stopped after the 429 |
| `Datacenter` | `https://www.uvp-verbund.de/freitextsuche?q=Datacenter` | Stopped after the 429 |
| `Data Center` | `https://www.uvp-verbund.de/freitextsuche?q=Data%20Center` | Stopped after the 429 |

The first correct search request returned HTTP 429. The public OpenSearch descriptor returned the same status. A Niedersachsen legacy descriptor URL returned HTTP 302 to the blocked UVP-Verbund descriptor. The capture did not bypass the block or request another result page.

The source result count remains null. Direct, context, and excluded counts also remain null. Zero would claim that a completed search found no records, which this capture cannot support.

## Rights decision

The portal imprint requires prior author consent for use of individual portal data and information. The current portal theme source at commit `085837f1d91748c90049ce78215842a69772c59b` matches that notice. The lane requires consent before commercial reuse or public redistribution.

The bundle retains response metadata and hashes. It does not retain HTTP bodies, result rows, applicant attachments, submissions, plans, images, maps, tiles, or personal fields. The assessment artifact may appear in a coverage index. Source rows may not enter the construction master, map, or current-coverage ledger.

## Interpretation boundary

UVP procedure labels describe regulatory process. They do not establish construction or operation. This release creates no facility identity, lifecycle status, workload type, power metric, PUE, or annual-energy estimate. It performs no site merge and leaves the unique physical site count null.

## Validation

The controlled probe recorded three requests with an eight-request cap and one-second minimum pacing. The inventory discloses one exploratory 429 request made before the controlled capture; that request did not retain response metadata. The builder stops result enumeration after an access block and uses bounded retries for server errors.

Validate the frozen assessment without network access:

```bash
python3 scripts/validate_germany_uvp_verbund.py
```

Run a new metadata-only probe in a fresh staging directory:

```bash
python3 scripts/fetch_build_germany_uvp_verbund.py --capture-only
```

The frozen v1 bundle lives at `source_assessments/germany-uvp-verbund-data-centre-search-2026-07-18-v1`. Directories use mode `0555`; files use `0444`.
