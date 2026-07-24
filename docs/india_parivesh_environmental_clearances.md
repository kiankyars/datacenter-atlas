# India PARIVESH environmental-clearance rights audit

The India lane is a lawful, metadata-only source assessment. PARIVESH is an
official high-signal planning and environmental-clearance source, but the
bounded rights audit did not establish permission to reproduce proposal-level
records. The current PARIVESH CMS copyright surface and the legacy
environmental-clearance copyright surface both condition reproduction on
permission. The legacy robots file allows root crawling; that is access
metadata, not a licence. The current host returned HTTP 404 for `robots.txt`.

The audit also checked the official data.gov.in catalog, its 2022 resource
metadata, and the Government Open Data License - India. That licence is
affirmative for resources separately published on data.gov.in. The cataloged
PARIVESH 2.0 resource is only a 386-byte state-level 2022 aggregate, published
and updated on 2023-06-15. It has no project-level discovery rows. The CSV was
not requested, and its licence is not treated as permission for records hosted
on PARIVESH itself.

The rights gate stopped before all proposal searches, result pages, project
details, and documents. No source response body or excerpt is retained. Result,
proposal, decision/publication, classification, project, site, and metric
statement counts are null; retained rows are exactly zero. The proposal search
was not executed, so observed source start and end dates are both null.

The future plan is predeclared but cannot run until explicit permission covers
proposal and result metadata and the technical interface is reverified. It uses
the exact case-folded literals `data centre`, `data center`, `datacentre`, and
`datacenter`. The 2006-09-14 lower bound is atlas-selected and aligned to the
date of the EIA Notification 2006. It is not evidence of PARIVESH record
availability, observed coverage, or completeness. The future plan clips annual
shards to that lower bound and 2026-07-18. It is capped at ten pages per
term-year query and 840 result-bearing requests total, paced at one request every
five seconds or slower. Cap, error, schema drift, or pagination ambiguity leaves
source counts null.

PARIVESH records regulatory planning and environmental-clearance workflow
status. That status is not evidence of physical construction or operation. This
assessment contains no data-centre type, coordinates, power, PUE, or energy
metric and is not eligible for the construction master, map, or current-coverage
ledger.

Validate the frozen bundle offline from the `datacenter_atlas` directory:

```bash
python3 scripts/validate_india_parivesh_environmental_clearances.py
```
