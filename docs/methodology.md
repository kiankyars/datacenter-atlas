# Data Center Atlas methodology

Status: initial operating specification, 2026-07-17.

## Objective and completeness contract

The objective is to identify, locate, and continuously track every discoverable data-centre
construction project worldwide. Literal completeness cannot be proven: small edge sites, interior
retrofits, urban conversions, underground facilities, and undisclosed projects can leave no visible
or documentary signal. The product therefore publishes two layers:

1. **Auditable construction census.** All purpose-built greenfield or expansion projects with either
   at least 10 MW of planned total facility load or at least 5,000 m² of visible external works.
2. **Unbounded leads.** Smaller, converted, speculative, secretive, or weakly evidenced candidates.

The thresholds are an initial detection floor, not an editorial importance cutoff. They may be
lowered as recall improves. Every release must report recall above the declared floor, coverage age,
source gaps, and an interval for the likely unseen population. A large row count is not evidence of
completeness.

## Units of analysis

The registry keeps these objects separate:

- **Campus:** a geographically coherent development containing one or more facilities.
- **Facility:** an independently operated or marketed data-centre unit.
- **Building:** a physical shell or data-hall building.
- **Project:** a dated development phase targeting a campus, facility, or building.
- **Power asset:** a substation, generation plant, or storage system serving one or more entities.
- **Organization role:** landowner, developer, owner, operator, tenant, utility, contractor, or
  financier.

A six-building campus is not automatically six independent facilities. A cloud region or
availability zone is a discovery lead, never a facility record. Stable entity IDs survive name,
owner, geometry, and status changes.

Deterministic within-release resolution is a review lane, not a write path. Exact typed source
identities, tightly gated same-kind site candidates, and explicit hierarchy candidates retain
both source families and upstream roots. Generated building/facility/project companions are
marked as structural relationships. Review-only releases and broad proximity-only matches are
excluded, and no candidate changes the canonical hierarchy until separately adjudicated with
evidence.

## Lifecycle

The detailed lifecycle is:

`lead → announced → site_control → permitting → permitted → clearing → civil_works → foundations → shell → MEP/electrical → commissioning → operational`

Side states are `paused`, `cancelled`, `repurposed`, `decommissioned`, `demolished`, and `unknown`.
The public aggregate `under_construction` means clearing through commissioning and requires recent
physical evidence or an authoritative construction-start record. An announcement, land purchase,
interconnection request, or future permit alone does not qualify.

Status is bitemporal. `as_of_date` describes when a claim applies in the world; `recorded_at`
describes when it entered this database. Contradictory claims are retained and grouped rather than
silently overwritten.

## Evidence and confidence

Every published claim must point to evidence. Evidence records preserve:

- source URL, publisher, retrieval time, publication time, and content hash;
- exact excerpt or document page/section when redistribution rights permit it;
- source family, so ten syndicated articles do not count as ten independent confirmations;
- imagery acquisition ID, date, sensor, resolution, license, and derived-artifact rights;
- extraction method, model version, analyst/model decision, and upstream claim IDs;
- valid time, location precision, calibrated confidence, and conflicts.

Preferred evidence order is: metered utility or regulator record; executed connection agreement or
final permit; operator/tenant filing; air permit or equipment schedule; installed electrical or
cooling equipment; calibrated floor-area prior; company announcement; reputable reporting; community
or social lead. Satellite imagery proves visible physical state, not owner, tenant, workload, or
energization by itself.

Separate confidence scores are required for existence/location, data-centre identity, construction
stage, operator/tenant, workload/type, power, and annual energy. `unknown` is preferable to a precise
guess.

## Type model

"Type" is not one mutually exclusive field. The registry records independently:

- service model: hyperscale self-build, hyperscale lease, wholesale colo, retail colo, neocloud,
  enterprise, sovereign/research, telecom/edge, or unknown;
- development: greenfield, brownfield, conversion, expansion, or unknown;
- workload: AI training, AI inference, HPC, general cloud, enterprise IT, mixed, or unknown;
- cooling: air-cooled, evaporative, chilled-water, direct-liquid-capable, other, or unknown;
- power topology: grid-only, grid plus onsite generation/storage, behind-the-meter, hybrid, or
  unknown.

Roof shape cannot establish an AI workload. Workload and tenant claims need documentary,
supply-chain, or clearly labelled probabilistic evidence.

## Power and energy

The following quantities must never be collapsed into a single `MW` column:

- requested, contracted, and energized grid capacity;
- total facility peak power;
- critical IT design, installed, and operational power;
- backup and prime generation nameplate;
- storage power and energy;
- average measured load and annual electricity consumption;
- average and peak PUE.

Every numeric claim carries a unit, low/base/high or P10/P50/P90 range, method, validity date, and
evidence. Correlated observations share a source family in the reconciliation model.

When annual consumption is not metered, it is labelled **modelled annual consumption**:

`TWh/year = IT_MW × PUE × load_factor × 8,760 / 1,000,000`

Under-construction facilities normally have design capacity and a forecast range, not actual energy
consumption. Generator redundancy, transformer reserve, and shared substations must be modelled
explicitly rather than treated as facility load.

## Discovery and verification

Discovery uses three partly independent channels:

1. permits, planning applications, land records, utility/regulator dockets, tax agreements,
   procurement, filings, contractor activity, company disclosures, news, and multilingual search;
2. expansion searches around known campuses, industrial parks, substations, transmission, fibre,
   power plants, and large land transactions;
3. recurring global optical and radar change detection, followed by targeted high-resolution review.

News search is a discovery queue, not evidence that a site exists or has reached a stated phase.
The [GDELT bulk-news lane](gdelt_news.md) screens one pinned non-consumptive title/quadgram snapshot
with a transparent multilingual lexicon and never fetches article bodies. Its URL candidates remain
outside confirmed releases until an analyst reviews the source article and independently
corroborates each facility, location, lifecycle, and numeric claim.

The [bounded Overture building lane](overture_building_discovery.md) screens full building
footprints using explicit approximate area and industrial-label thresholds. It preserves GERS and
upstream source identities and labels exact or nearby v3 atlas references without merging. A
footprint candidate remains outside the atlas until independent evidence establishes that it is a
data centre and separately establishes lifecycle, operator, workload, and any numeric claims.

The [Google Open Buildings Temporal lane](open_buildings_temporal.md) reads annual 2016-2023
building-presence, fractional-count, and presence-screened height signals for one bounded AOI. It
preserves the dataset's 4 m effective resolution despite its 0.5 m storage grid and treats temporal
change only as an unstable model signal requiring review. Nearby v3 atlas entities are stored as
non-merging priors and never determine candidate identity or selection. Because both this product
and the atlas Sentinel-2 CV lane derive from Copernicus Sentinel-2, they share one provenance root
and cannot corroborate each other as independent evidence families.

The imagery system first proposes grading, slabs, shells, substations, and equipment yards. A
high-resolution confirmation stage detects the combination of repetitive halls, cooling equipment,
generator rows, substations, secure service yards, and construction evolution. Warehouses, cold
storage, semiconductor fabs, battery plants, hospitals, greenhouses, and ordinary power projects are
explicit hard-negative classes.

Optical and radar models use site-level geographic and temporal holdouts. Random neighboring-tile
splits are prohibited because they leak campus appearance. Computer vision creates dated evidence
observations; it never directly declares the operator, workload, or megawatts.

## Release gates

A public census release requires:

- 100% claim-level lineage for published fields;
- at least 95% precision for `confirmed data centre` on a blind review sample;
- at least 90% recall on a held-out known-site sample above the declared detection floor;
- lifecycle macro-F1 of at least 0.80 and median event-date error at most 30 days;
- calibrated 80% power intervals covering 75–85% of blind ground truth;
- duplicate campus/phase rate below 1%;
- country-level coverage age, source availability, and known blind spots;
- a random-cell audit and multi-list capture-recapture estimate of residual unseen sites.

No claim of parity with SemiAnalysis is allowed until both products are compared on a lawfully
licensed common snapshot, normalized to the same campus/facility/building/phase ontology.

The checked [public/open coverage audit](coverage_audit.md) operationalizes that gate without
claiming parity. It measures every redistribution-cleared child by release, source family, and
country; separates review-only leads from non-review rows; reports field and freshness gaps; and
leaves confirmed duplicates and unique physical sites null. A larger Scrutica-inclusive audit is
retained only for local research because upstream reuse rights are not fully evidenced. The
SemiAnalysis comparison is restricted to public count and methodology statements. The licensed
row-level comparison and parity decision remain pending.

## Publication safeguards

The public product includes infrastructure facts needed for market and energy analysis but excludes
personal contact details, access-control layouts, security procedures, exploitable equipment
vulnerabilities, and unlawfully acquired imagery. Restricted imagery stays in a rights-controlled
store. Public outputs retain all required source attribution and use coarser location precision when
law, safety, or source terms require it.

Share-alike compilations are partitioned by release boundary, not merely labeled in a mixed table.
In particular, the Scrutica discovery layer uses a dedicated SQLite database and dedicated local
release. Scrutica's displayed CC-BY-SA label is not accepted as proof of rights for an upstream
source: the PeeringDB audit found 1,548 dependent rows with no recorded permission or upstream
license basis. The mixed-rights child is quarantined from redistribution until every upstream
family is cleared. It may produce local advisory resolution links to open-source entities, but its
records are never automatically merged into the ODbL/CC0 open release or treated as independent
corroboration of the upstream source named in Scrutica's provenance fields.

Cross-release resolution therefore runs as a separate hash-pinned review bundle. It opens each
child database read-only, preserves left/right entity and evidence IDs, and records whether the
records share an upstream provenance root. Candidate links never alter either child and never imply
a unique-site count; accepted or rejected identity decisions require a later evidence-backed
adjudication layer.
