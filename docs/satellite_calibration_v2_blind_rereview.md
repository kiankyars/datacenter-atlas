# Algorithm-v2 identity-blind rereview audit

The independently accepted successor at `satellite_calibration/2026-07-19-algorithm-v2-blind-rereview-v5` records a closed, identity-blind visual rereview of the 36 ready algorithm-v2 comparisons and preserves seven additional rows as `blocked_multitile_required` without assigning them a v2 decision. Its manifest SHA-256 is `dff606bfbd4015c51d24387d4b9a73a48b236895d745b7343aacfe46a5ef57e7`. Fresh independent QA reproduced the exact frozen release through both API and CLI publication, verified every source and builder pin plus the scientific arithmetic, exercised explicit payload-write and publication-fsync failures, found no descriptor leaks, and confirmed v1 through v4 remained byte-identical.

V4 is byte-preserved as rejected historical evidence. A fresh independent audit proved that a target substitution performed during the normal successful parent-fsync call could occur after v4's last target-identity check; the writer returned success and a release ID while the public pathname held an unrelated `0755` marker tree. V5 preserves v1 through v4 byte-for-byte and changes publication mechanics only. It binds the output parent and staged tree through open descriptors, uses an atomic no-clobber directory rename, fsyncs staging creation and every later directory-entry mutation, and after the publication fsync rechecks the parent path, target identity, absent staging name, exact frozen file identities, modes, and bytes before checking the target binding again.

Failure recovery is deliberately conservative. Portable POSIX APIs do not provide an atomic "unlink this pathname only if it still names this inode" operation. V5 therefore performs no recursive deletion after a publication failure. It may atomically quarantine a writer-owned public target, fsync that rename, and retain it for explicit inspection. If a substitute races the quarantine check, v5 detects the moved inode, preserves it, and attempts a no-clobber restoration. The primary failure and every inspection, rename, restoration, and fsync failure are reported together. This can leave a writer-owned staging or quarantine directory after a failed call; that is an intentional safety property, not a successful publication.

The writer requires the output parent to exist already as a regular, non-symlink directory; it does not create arbitrary parent chains.

The deterministic rule resolves A/B agreement directly. It sends exactly the eight A/B disagreements to independent reviewer C, uses a two-of-three majority when C matches A or B, and otherwise assigns `uncertain`. Historical labels are joined only after those decisions are fixed.

The result is 16 retain, 19 reject, and one uncertain. The decision basis is 28 A/B agreements, seven two-of-three majorities, and one three-way uncertain. Of 35 binary-comparable reviewed rows, 30 match the prior analyst label, or 85.71428571428571% raw label agreement. This is descriptive agreement—not accuracy, precision, recall, truth, production calibration, threshold validation, construction truth, or SemiAnalysis parity.

Retention means only coherent site-scale physical change is visible in the comparison pixels. It is not a data-centre identity, lifecycle, type, operator, power, energy, PUE, or workload claim.

The release README and `protocol-deviations.json` disclose both deviations: reviewer B briefly exposed blind `after.png` paths but opened no extra images or metadata, so identity blindness was not compromised; and the orchestration operator accidentally printed three sealed lineage rows after A/B closed but before C finished. C was fork-isolated, received only eight blind IDs with no labels or history, and the operator did not adjudicate, so C remained uncontaminated.

Validate offline with:

```sh
python3 scripts/build_satellite_calibration_blind_rereview.py \
  --definition sources/satellite-calibration-2026-07-19-algorithm-v2-blind-rereview-v5.json \
  --output-dir satellite_calibration/2026-07-19-algorithm-v2-blind-rereview-v5 \
  --validate-only
```
