# Singapore URA Planning_Decision assessment

This source lane assesses the official Singapore Urban Redevelopment Authority
`Planning_Decision` API without acquiring credentials or capturing records. It
is deliberately fail-closed.

## Access and controlled audit

URA's [API documentation](https://eservice.ura.gov.sg/maps/api/) requires an
AccessKey obtained through the
[registration page](https://eservice.ura.gov.sg/maps/api/reg.html) and a token
generated for the day's API access. Registration asks for company or individual
particulars and presents a CAPTCHA. No registration was submitted, no CAPTCHA
was automated, and no credentials were requested or retained.

The frozen assessment hash-binds exactly seven controlled GETs: API docs,
registration, the API-specific
[Open Data Licence](https://www.ura.gov.sg/eservices-info/maps/acceptance-grant-licence/),
[API terms](https://www.ura.gov.sg/eservices-info/maps/api-terms-of-service/),
[robots.txt](https://eservice.ura.gov.sg/robots.txt), and unauthenticated token
and `Planning_Decision&year=2025` probes. The direct licence and terms GETs
returned HTTP 403 from CloudFront. The unauthenticated API probes returned HTTP
200 but application-level `Error` envelopes with string `Result` values. Their
parsed status/message metadata and response hashes are retained; bodies are not.

An API response can produce a count only when all three gates pass: HTTP status
200, top-level `Status` exactly `Success`, and `Result` an array. An HTTP 200
`Error` envelope is a failure and never evidence of zero records.

## Future authorized plan

The official documentation says annual records are available only after 2000,
while related catalogue wording has described coverage from 2000. The plan
therefore predeclares a year-2000 boundary probe and separate annual requests
for every year 2001 through 2026. None has been executed.

After an authorized annual capture, the documented daily delta uses
`last_dnload_date=dd/mm/yyyy`, may look back no more than one year, and cannot be
combined with `year`. A delta row with `delete_ind == Yes` tombstones the exact
`dr_id`. The record unit is one row per exact `dr_id`; addresses and lot numbers
do not authorize automatic merging.

Direct phrase vocabulary is `data centre`, `data center`, `datacentre`,
`datacenter`, `data-centre`, `data-center`, `data farm`, and `data-farm`.
`server farm`, `server-farm`, `computer centre`, `computer center`, `server
room`, `co-location`, and `colocation` require review. `DC`, `cloud`, `data`, or
`centre` alone are never accepted.

## Fail-closed atlas boundary

Every result, decision, search, permit, project, site, classification, and
metric count is null; retained source rows are zero. Planning decisions and
Written Permission are regulatory records, not physical construction or
operating milestones. The assessment makes no coordinate, facility-operator,
data-centre-type, capacity, power, PUE, or energy inference.

The [Development Register polygon dataset](https://data.gov.sg/datasets/d_5fea232c6e60ea4a896e355e3c05141c/view)
is a separate unjoined source: its polygon identifier is not documented as a
`Planning_Decision.dr_id` join key. Construction-master, map, and current-ledger
imports remain false until an authorized row capture exists and is reviewed.

## Reproduction

The release directory is mode `0555`; every file is `0444`. The builder derives
all files offline from the pinned audit metadata. The validator rejects
noncanonical JSON, symlinks, mode drift, hash drift, counter drift, and derived
file tampering.

```bash
python3 scripts/validate_singapore_ura_planning_decisions.py
python3 scripts/build_singapore_ura_planning_decisions.py \
  --output /tmp/ura-planning-release
```
