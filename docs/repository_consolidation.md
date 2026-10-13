# Repository consolidation — 13 October 2026

Data Center Atlas is the maintained home for data centre research and publication.
Semiconductor Atlas publishes semiconductor facilities again. Its earlier `datacenters/`
directory remains a historical archive; new data centre work belongs here.

The combined data preserves the 231 original project records and their 1,109 source references.
Eleven records enrich an existing project. Twenty-one describe a different or broader project
scope at an existing site. The other 191 independently identified source records add sites.
This gives 389 sites, 413 projects, 2,038 evidence rows and 53 countries.

The following country-research update adds NorthC FRA01 and refreshes Frontier and The Barn,
bringing the current inventory to 390 sites, 414 projects and 2,046 evidence rows. Its separate
`2026-10-13-research` archive preserves the consolidation snapshot and all source records.

Six multi-site programs and two unresolved identities remain in the project catalogue and
downloads without adding to site or project totals. For example, Microsoft's Licking County
program covers several campuses; its record must not become another site. The initial HUMAIN
Riyadh record may overlap Al-Saad, and Microsoft Fairwater Atlanta may be a tenant project at
QTS Fayetteville. The source records and reasons for each decision remain available.

## What survives

- `source-records.json` preserves every original field, source URL, source-local ID, publication
  date, access date, metric qualifier, unit, scope, milestone and note. Original file hashes and
  the source repository commit identify the inputs.
- `identity-mapping.json` records every matching decision, campus/phase distinction and hold.
- `project_details_json` embeds the complete source records on the projects they describe.
  Their `source_evidence_ids` maps local source IDs to the unified evidence table.
- Existing project IDs, selected statuses, observation dates and reviewed locations remain.
  Conflicting or broader source claims remain explicitly dated in their own records; a newer
  review date does not overwrite a physical observation.
- Figures and timelines are readable on site pages, included in JSON/CSV/SQLite and flattened
  into separate Excel sheets. Original project URLs continue at `projects/<source-id>/`.

An imported record's location retains its original precision. Locality, county and region
points do not establish the facility's position. Sources include primary disclosures and
secondary reporting. Importing them is not a new verification pass or an application of the
90-day rule to historical records. New research still follows the admission rules.

Imported evidence hashes identify the retained factual record projection, not a newly fetched
publisher page. Publication month precision and unknown dates remain explicit. Third-party
source terms are not inferred from the Atlas data license.

## Reproduce

```sh
python3 scripts/build_consolidated_dataset.py \
  --input definitions/atlas-consolidation-2026-10-13.json --validate-only
python3 -m unittest tests.test_consolidation tests.test_dataset_update tests.test_project_details
```

The input definition pins both source objects and the reconciliation by SHA-256. The new
`2026-10-13-consolidated` directory leaves the previously published `2026-10-13` files unchanged.
The suffix distinguishes two data archives on the same day; public pages display the date.
Later data updates must preserve the standalone source records and resolution metadata as well
as linked project details.

All branches in the data centre repository already converge on `main`. Semiconductor Atlas's
producer fixes and completed-milestone branch were merged into its `main`; its historical
study runtime and source evidence remain preserved separately. Branch ancestry and publication
are checked before reporting the consolidation as deployed.
