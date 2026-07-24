# IAAC official-registry assessment lane

This isolated source lane assesses one exact Canadian Impact Assessment Registry project search:

`https://iaac-aeic.gc.ca/050/evaluations/exploration?search=data%20center&document_type=project&culture=en-CA`

The 2026-07-18 local-date capture returned 41 project observations on one page. Every result is retained and has an explicit decision: four direct observations and 37 exclusions. The lane does not update the construction master, map, ledger, benchmark, or shared source documentation.

## Direct observations

| IAAC reference | Observation role | Source power wording | Interpretation boundary |
|---|---|---:|---|
| 90514 | Bell AI Fabric Data Centre Project | 300 MW industrial artificial-intelligence data centre | Preserve the wording. It is neither IT capacity nor annual energy. The source also says 65-hectare agricultural site. |
| 90036 | Mihta Askiy supporting-generation project | 650 MW production capacity | Generation capacity supporting a new data centre; never data-centre load or consumption. |
| 90123 | Beacon Heartland supporting-generation project | about 920 MW production capacity | Generation capacity supporting a new data centre; never data-centre load or consumption. |
| 90121 | Beacon Indus supporting-generation project | about 1,494 MW production capacity | Generation capacity supporting a new data centre; never data-centre load or consumption. |

All four are observations, not four resolved facilities or sites. Unique physical site count is null. No PUE, annual energy, IT capacity, operating model, or operation date is inferred.

IAAC `Completed` is assessment-process status, not physical lifecycle. The three Alberta source descriptions use proposal wording. Bell's June 5, 2026 latest update says the carrying out of physical activity had substantially begun; this is dated construction evidence only and does not verify operation.

## Exclusion boundary

The other 37 results remain in `search-inventory.jsonl` with row-level reasons. Three concern ancillary work at existing data-centre assets: fencing, chiller/dry-cooler replacement, and transformer/switchgear removal. One is a seismic-data processing satellite hub rather than a general-purpose data-centre build. The remaining 33 are non-data-centre projects matched through generic `data` and `centre`/`center` context.

No excluded project page was fetched.

## Retrieval and rights

The bounded retained capture made 11 successful requests, paced at a minimum of one second with a 20-request cap and retry backoff:

- one exact search page;
- four direct IAAC project pages;
- three IAAC geospatial landing pages that explicitly state Open Government Licence–Canada availability; and
- the three ZIP files linked by those licensed landing pages.

No public comment, submission, PDF, initial project description, image, or other linked attachment was requested. ZIP member names and sizes are inventoried without opening member bodies or extracting nested archives.

The general Canada.ca terms allow non-commercial reproduction subject to stated conditions and require prior written permission for commercial redistribution unless otherwise specified. Search and project HTML is therefore audit-only and not publication-eligible here. Only the three geospatial archives receive the OGL-Canada scope explicitly stated on their IAAC landing pages. Third-party material is not assumed to be open.

## Reproduction

The frozen bundle is `source_assessments/iaac-data-center-search-2026-07-18-v1` with directories at mode `0555` and files at `0444`.

Validate without network access:

```bash
python3 scripts/validate_iaac_registry.py
```

Rebuild from an existing retained staging capture without network access:

```bash
python3 scripts/fetch_build_iaac_registry.py \
  --resume \
  --staging-dir .staging/iaac-data-center-search-2026-07-18-v1 \
  --output /path/to/new/iaac-data-center-search-2026-07-18-v1
```

The builder refuses to overwrite an existing output. The offline validator checks the closed request set, all raw hashes, exact 41/4/37 arithmetic, explicit classification decisions, project fact contracts, licence landings, ZIP safety inventory, derived-file reproduction, manifest, and sidecar hash.
