# Satellite and computer-vision pipeline

Status: architecture plus two bounded Sentinel-2 pilots, 2026-07-17.

The checked Colossus 2 pilot exercises the first deterministic path end to end: two separately
bounded Earth Search STAC queries, exact response hashes, season-near low-cloud scene selection,
windowed COG reads, per-band STAC scale/offset application, SCL masking, co-registration, index and
absolute-reflectance change, connected-component proposals, PNG review views, GeoJSON, and a hashed
report. The output is stored under `satellite_evidence/colossus-2-2024-2026/`. It confirms that the
pipeline can surface visible construction-scale change; it does not validate global recall or
identify an unknown site.

The checked Ada Docklands pilot repeats the path over a second, independently documented
under-construction project. A site-cropped, season-matched 2024/2026 pair has 100% mutually valid
pixels and proposes three connected optical-change components totaling 9,100 m². An earlier
scene-wide-cloud-selected pair was rejected because the parcel itself was cloud-obscured; this
demonstrates why production catalog selection must score the AOI-level SCL mask before accepting a
pair. The components remain review-only changed pixels, not data-centre floor area.

Satellite imagery is one evidence channel in a candidate-first census. It is good at dating external
construction and confirming site form; it is poor at finding interior retrofits, proving
commissioning, identifying secret tenants, or measuring electricity directly.

The [deterministic satellite-review queue](satellite_review_queue.md) now provides the narrow bridge
from a release atlas to the existing catalog and change scripts. It orders coordinate-bearing
campuses, facilities, and projects by lifecycle information value, emits bounded per-AOI argument
arrays, and hash-binds both its source release and queue artifact. Within a lifecycle tier it sends
missing and older status evidence to review first, while preserving effective country fields and
reporting country/tier and freshness counts for balance audits. Its closed three-file output is
strictly validated and directory-atomically published. Queue construction is offline and does not
infer identity, lifecycle, operating status, or power from imagery.

The [resumable catalog batch](satellite_batch.md) executes that verified queue sequentially under
explicit job and HTTP-attempt caps. It remains catalog-only and revalidates every completed response
bundle before resume; change detection and lifecycle interpretation stay in the reviewed lane.

## Processing tiers

### Tier 1: global open-data proposal scan

Run quarterly over land and monthly over priority industrial/grid cells. For each analysis tile:

1. Query Sentinel-2 L2A through the [Copernicus Data Space STAC API](https://documentation.dataspace.copernicus.eu/APIs/STAC.html).
2. Mask cloud, cloud shadow, and snow; harmonize processing baselines; build season-matched reference
   and recent composites.
3. Add orbit-specific, incidence-normalized Sentinel-1 RTC/GRD VV/VH time series for cloud-prone,
   winter, and tropical regions.
4. Add Landsat 8/9 as an independent historical and thermal-context channel.
5. Calculate vegetation loss, bare-soil and impervious gain, roof emergence, road/pad growth,
   spectral CUSUM, SAR change, rectilinearity, and proximity features.
6. Retain both a deterministic change detector and a learned Siamese/temporal segmentation model.
   The deterministic path makes missed events and model drift auditable.

The proposal classes are grading/clearing, civil works, foundation/slab, shell/roof, substation or
transmission work, cooling/generator yard, and ordinary industrial construction. Sentinel-2's 10 m
bands are sufficient for large site change but not detailed equipment recognition. Sentinel-1 IW
10 m pixel spacing must not be described as true 10 m resolution; spatial resolution is roughly
20 × 22 m.

### Tier 2: candidate ranking

Rank proposals with documentary and geospatial context rather than hard-filtering them:

- permits, planning records, company disclosures, land transfers, tax agreements, job postings,
  contractor awards, and utility/regulator records;
- known campus expansion buffers, large substations, transmission, generation, fibre, water, and
  suitable industrial land;
- repeated large building modules, high site power density cues, construction velocity, and prior
  operator archetypes;
- novelty and expected information gain.

Grid or fibre proximity can raise priority but cannot be mandatory: remote and behind-the-meter
projects would be systematically missed.

### Tier 3: licensed high-resolution confirmation

Purchase or task commercial imagery only for ranked areas of interest. Contract rights must cover
the intended ML training, derived coordinates/features, retention, contractors, redistribution, and
model weights.

Segment and track:

- building shells, roofs, and repeated hall modules;
- roof/perimeter cooling equipment and liquid-cooling support plant;
- generator rows, exhaust stacks, fuel tanks, and battery systems;
- substations, transformers, buswork, transmission feeds, and onsite generation;
- temporary laydown, construction equipment, roads, parking, and service yards.

Build a temporal site graph over these objects. A data-centre identity decision requires several
mutually supporting features plus documentary corroboration. Hard negatives include warehouses,
cold storage, semiconductor fabs, battery factories, hospitals, greenhouses, distribution centres,
and standalone power projects.

### Tier 4: analyst adjudication

The review queue displays before/after imagery, independent documentary sources, proposed entity
matches, model probabilities, and conflicts. Reviewers can confirm a visible event, reject a hard
negative, split or merge entities, request newer imagery, or leave the site unresolved. Every action
is versioned and becomes training feedback.

## Lifecycle inference

Use a monotonic semi-Markov model with evidence timestamps:

- **clearing:** sustained vegetation-to-bare-soil transition;
- **civil works:** access roads, drainage, grading, and pads;
- **foundations:** slab or column-grid pattern;
- **shell:** walls and roof completion;
- **MEP/electrical:** cooling, generators, and electrical yards;
- **commissioning:** complete external plant plus utility, permit, or company evidence;
- **operational:** certificate, utility, or operator evidence preferred.

Night lights, thermal change, and parking activity are corroboration only. They cannot independently
prove operation or estimate MW. Pauses, cancellations, demolitions, and repurposing remain possible
after any early phase.

## Power estimation from imagery

Imagery-derived capacity is a probabilistic observation, never ground truth. Candidate estimators
include:

- identified cooling model and unit/fan count, adjusted for climate design point and architecture;
- transformer MVA, power factor, utilization, reserve, and shared-substation allocation;
- generator model/count, duty rating, redundancy, and permit operating limits;
- white-space/floor area with operator-, vintage-, cooling-, and workload-conditioned priors.

Reconcile these with permits, connection agreements, company statements, and metered values in a
hierarchical model. Return P10/P50/P90. Keep requested grid, contracted grid, facility peak, critical
IT, backup/prime generation, storage, and annual consumption separate.

Epoch AI's public [methodology](https://epoch.ai/data/data-centers-documentation/methodology)
reports that its calibrated 80% IT-power interval is within a factor of 1.4 of the actual value.
Matching or improving this on a larger geography-held-out blind set is the initial external bar.

## Training and evaluation

Split by site, geography, operator, climate, vintage, and time. Neighboring tiles from one campus
must never span train and test. Maintain three gold sets:

1. known construction timelines across clear, cloudy, snowy, tropical, desert, and dense-urban
   conditions;
2. site-level identity labels with explicit hard negatives;
3. power ground truth from metering, executed connections, or final permits.

Primary metrics are proposal recall/precision, median and P90 detection lag, change IoU/F1, VHR
object AP, lifecycle macro-F1, event-date MAE, identity Brier score/ECE, power absolute log error and
bias, and empirical interval coverage. Report all metrics by region and size band.

## Storage and cost control

Process cloud-optimized imagery in place. Store STAC item IDs, compact seasonal composites, change
maps, derived geometries, model outputs, and hashes rather than copying global archives. Restricted
imagery stays in a rights-controlled object store. Target commercial imagery by expected information
gain; global high-resolution blanket coverage is neither necessary nor economically credible.

## Known blind spots

- persistent cloud, snow, shadow, SAR speckle/layover, and poor co-registration;
- small, underground, high-rise, converted, or interior-only projects;
- speculative grading, stalled builds, cancellations, and repurposing;
- novel or indoor cooling, shared substations, and generator redundancy;
- shell companies, secret tenants, stale footprints, and sparse public permits;
- geographic, language, operator, and public-market bias;
- license/API changes and architecture drift as liquid cooling and onsite power evolve.
