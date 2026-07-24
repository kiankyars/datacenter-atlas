# EPA ECHO and Facility Registry Service

EPA ECHO and the Facility Registry Service (FRS) are useful U.S. identity and permitting-context
sources, but neither is a data-centre census. The checked assessment implements one conservative,
local review pilot and does not add records to an Atlas release.

The immutable bundle is `source_assessments/epa-echo-frs-2026-07-18-v1/`. Its manifest SHA-256 is
`bcd50875c4862033cbc0fcda1e83611cec7a58cf504b3e85734b28cfdeb30bd6` and is validated offline.

## Access boundary

[ECHO web services](https://echo.epa.gov/tools/web-services) are public, query-only GET services.
EPA explicitly directs large-volume users to ECHO Data Downloads. The pilot therefore issued one
`get_facilities` request with `p_ncs=518210` and `responseset=1000`, made no pagination request, and
did not run a REST bulk loop. The response reported `QueryRows=928` at
`2026-07-18T22:05:18Z`. That is a time-bounded count for a broad NAICS filter, not U.S. completeness
and not proof that all 928 records are data centres.

FRS links records that refer to the same facility, site, place, or program interest across EPA
program systems. The [ECHO FRS download summary](https://echo.epa.gov/tools/data-downloads/frs-download-summary)
documents FRS Registry IDs, names, addresses, NAICS/SIC codes, available coordinates, and program
links. It also states that ECHO's file is not a complete FRS download. An FRS Registry ID is useful
identity evidence but is not, by itself, proof of one unique physical Atlas site.

## Rights boundary

The Data.gov record for the
[EPA FRS Facility Interests dataset](https://catalog.data.gov/dataset/epa-facility-registry-service-frs-facility-interests-dataset-download)
is public, marked CC0 1.0, and was modified on 2026-07-05. That license marker is scoped to the named
dataset download. It is not transferred to all ECHO program records or to referenced third-party
data. EPA's [geospatial disclaimer](https://www.epa.gov/web-policies-and-procedures/epa-disclaimers)
also says EPA-produced geospatial data are public domain unless otherwise specified, while
referenced third-party data may have separate rights.

This pilot did not checkpoint and join the exact CC0 Facility Interests distribution, so it does
not claim exact field-level CC0 lineage for its four rows. All four remain local, review-only, and
not publication eligible. A publication lane must first fetch the official dataset download,
checkpoint its exact distribution, and verify each retained identity or location field against it.
This is a conservative source-governance decision, not legal advice.

## Four name-token leads

The pilot preserves four FRS identities supplied by the bounded review:

- `110070205789`, `SYCAMORE ORANGETOWN - DATA CENTER BUILDING`, Orangeburg, New York;
- `110071506594`, `NVA13 - DATA CENTER SITE PLAN`, Manassas, Virginia;
- `110071509321`, `NTT GLOBAL DATA CENTER VA10 EARLY GRADING PLAN`, Gainesville, Virginia; and
- `110071854750`, `SDC DFW-VII DATA CENTER PHASE 2`, Garland, Texas.

These are name-token leads only. A facility name containing “data center,” “site plan,” “grading,”
“building,” or “phase” is not physical-construction verification. The pilot explicitly excludes
FRS `110070251348`, `JE DUNN CONSTRUCTION`, because a contractor name is not a data-centre site
identity, and excludes the generic `INTERNATIONAL BUILDING` match.

All four rows have null coordinates, lifecycle, data-centre type, gross power, IT load, annual
energy, PUE, operating model, and operational workload. There are zero construction-verified,
typed-capacity, typed-energy, typed-PUE, typed-workload, publication-eligible, or merged rows. The
unique physical-site count is `null`.

## Fail-closed use

The pilot must not:

- infer data-centre identity from NAICS 518210 alone;
- infer construction from a facility name;
- infer capacity, energy, PUE, workload, or type from a name or industrial code;
- treat an FRS Registry ID as a unique physical-site count;
- transfer the Facility Interests CC0 marker to all ECHO records; or
- merge any row into the Atlas without separately licensed evidence and analyst review.

The validator is offline and checks canonical JSON, exact row identities, null-field controls,
source checkpoints, the manifest, and its sidecar:

```sh
python3 scripts/validate_epa_echo_frs_assessment.py
```
