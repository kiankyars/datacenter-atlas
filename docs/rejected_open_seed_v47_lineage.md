# Rejected open-seed v47 lineage

Open-seed v47 and its downstream federation, coverage, construction-master, and
construction-map artifacts are retained as immutable historical evidence. They
are not accepted successors and must not be used by a public-current ledger or
by a later release as an immediate predecessor.

## Why the branch is rejected

The accepted seed sequence is v44 to v45 to v46. V45 added eight VNET Q1 2026
inputs and v46 retained them while adding ten Goodman Q3 FY26 inputs. V47 was
instead built directly from v44. Its own test forbids reading v45 and v46, and
the resulting release removes all accepted Goodman rows and rewrites the VNET
identity topology.

The timestamp sequence rules out an unavoidable build race: v46 and its
Goodman inputs existed before v47's recorded time. The fork was therefore a
deliberate but invalid predecessor choice.

V47 also contains two source-level acceptance problems:

- The STACK Stafford record turns a statement about the first topping-out at a
  named technology campus into a specific anonymous data-centre project. The
  retained text never identifies what type of campus structure topped out.
- The DigiPower record's normalized shell status is supported, but one metadata
  phrase says prior site and civil work was completed or superseded when the
  source only says the project was transitioning to vertical construction.

The eight VNET v2 inputs are an identity migration, not new evidence. They
replace two regional non-geographic anchors with eight locality-scoped
technical campus entities even though the source does not prove eight unique
physical campuses. They also retain stale guardrail text describing the old
two-anchor model. VNET v1 therefore remains accepted until a separately
reviewed migration and crosswalk exist.

## Retained rejected artifacts

The rejected branch comprises:

- `sources/open-seed-2026-07-20-v47.json` and
  `releases/2026-07-20-open-seed-v47`;
- `sources/federation-2026-07-20-public-open-v22.json` and
  `federated_indexes/2026-07-20-public-open-v22`;
- `sources/coverage-audit-2026-07-20-public-open-v21.json` and
  `audits/2026-07-20-public-open-coverage-v21`;
- `sources/construction-master-2026-07-20-public-open-v21.json`,
  `sources/construction-map-2026-07-20-public-open-v21.json`, and their v21
  master and map bundles;
- the construction v5 carrier modules, scripts, and v21 regression test.

Keeping these bytes makes the failed lineage auditable. It does not make their
rows public-current, globally additive, or a count of unique physical sites.

## Accepted predecessor chain

Until a corrected successor is frozen, the accepted public-current chain is:

- open seed v46;
- public-open federation v21;
- public-open coverage audit v20;
- public-open construction master and map v20;
- current-coverage ledger v15.

All of those artifacts retain null unique-physical-site counts and explicit
false global-completeness and benchmark-parity claims.

## Salvage boundary

A corrected seed successor must start from v46, retain Goodman v1 and VNET v1,
and add only independently accepted new inputs. Alto SP01, Galaxy Helios Phase
II, Hut 8 Beacon Point, and Kasi LOS1 passed source review. DigiPower may be
added only through a corrected, separately pinned source version. STACK and the
VNET v2 migration remain excluded.

Future federation, coverage, construction, and current-ledger successors must
likewise start from the latest accepted predecessor rather than the rejected
v47 branch.
