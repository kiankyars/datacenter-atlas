# Sentinel mosaic-v3 blocked-row preparation

The accepted immutable `satellite_mosaic_preparation/2026-07-19-algorithm-v2-blocked-v6` successor prepares the seven algorithm-v2 calibration rows that stopped at a single-scene boundary. It derives bindings only from already archived STAC responses under the accepted `sentinel-2-l2a-change-mosaic-v3` contract. Six rows are metadata-ready with one explicitly hash-bound adjacent-tile companion in each epoch. `satq-3a5dbdef8b0fd5a8f4e53bf1` (MRS5) remains blocked: the archived baseline response contains the required 31TFJ companion, but the archived current response does not.

V1 through v5 are rejected and preserved byte-for-byte as publication-mechanics evidence. V5 fixed v4's ambiguous create-then-`FileExistsError` and sequential final-close defects, but an independent v5 audit found that descriptor acquisition still sat outside the outer cleanup ledger. An initial target-stat failure after the writer opened its parent could leak that descriptor; a validator identity failure followed by a post-close error could replace the primary failure and lose the structured path report. V6 registers every directory descriptor immediately after `os.open` returns and aggregates acquisition, recovery, and cleanup failures. A fresh independent audit accepted v6 after socket-denied API and CLI publications reproduced all frozen bytes, every source and builder pin reconciled, and an independent seven-scenario fault harness found no false success, raw exception escape, or descriptor growth.

This is preparation only. It made zero network requests, downloaded and opened zero imagery assets, and performed zero mosaic executions. A metadata-ready specification does not establish asset availability at a later execution time or any data-centre identity, lifecycle, type, operator, capacity, power, energy, PUE, workload, construction truth, production calibration, or SemiAnalysis parity.

The release contains six `mosaic-specs.jsonl` rows and one `blocked.jsonl` row. Every row pins its queue ID, blind item ID, entity, AOI bounding box, baseline/current epoch labels, archived response path and hash, primary item ID and canonical item hash, companion item ID and canonical item hash, asset-grid coverage, accepted module/CLI pins, and the original aggregate/rerun row hashes. `source-inventory.json` closes 40 input file pins. The v6 `blocked.jsonl`, `mosaic-specs.jsonl`, and `source-inventory.json` bytes are identical to v2 through v5; only version, builder, publication-contract, README, summary, and manifest metadata change.

Accepted mosaic-v3 processor pins remain:

- module: `68a89c8aedd16326c530d3c07416a10432e64af1458dba630ded89d4b5ace071`
- CLI: `6e5ffc0dbb04a1f8202d13556e26fe45a9075966da9037e70f417152360e2183`

Publication lineage:

- rejected v1 definition: `24b18962bea7f45d06f84a0a93d9c1eba8ba332b94077eb3d2d4e9afe8003ba8`; manifest: `8d18820f75be42534ad0f26f893f7830787c1b4d42c9e6700d331985a1b67b5f`
- rejected v2 definition: `92c45ec8d6f4058a182411282dfc5314d4e6208f9f9dfd77e804b99265237cae`; manifest: `9e0e0144bb20fd29c52409eee1209bbc91e79908ae5338e77376429773734240`
- rejected v3 definition: `6da293ff7d53fe044f76e2b253723d7f56719f30a67c94ba3155762146670967`; manifest: `f39c433e2954026e7f9fe56fea226271483e98e5ee9f75a2ce2443483ecc1d4b`
- rejected v4 definition: `f054706117ca698cf0871da24efab31c71aed7c6d0bae48ec093c82db4d9e019`; manifest: `fe25a98ab53ff2edb865286129f2b6767f66d667a34e22d69773e202a0a5650b`
- rejected v5 definition: `cf566ec4d747c11bba4ac9e58975629ca41749b3b1be1c07db7841a9e1ba6f70`; manifest: `402fb82275f72f5b91ddd6c45c71e45723e3c62b2c127fa2366a1d161fab2109`
- accepted v6 successor definition: `3c8920f5d0779f9286da0361f0256efb285d84e842aaa74083b1b8d08a5e95b1`; manifest: `f0cb59766c68e7cc54da8f103f7a92a7eb4943e2fe4533702df9d19c0cd366e6`
- v6 publisher module: `c793935f276aa33b1ed97b8d7ae5af10794ce41d00327b0ef4918e533a4e72f4`; CLI: `979cfc9eec3fbf0810bbc4bb8d4433c504a0b232b12e32b7d3f2b3851592eb22`

Reproduce and validate offline with the already cached pinned metadata runtime:

```bash
UV_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 \
uv run --python 3.12 --with rasterio==1.5.0 \
python scripts/build_satellite_mosaic_preparation_v6.py \
  --validate-only \
  --definition sources/satellite-mosaic-preparation-2026-07-19-algorithm-v2-blocked-v6.json \
  --output-dir satellite_mosaic_preparation/2026-07-19-algorithm-v2-blocked-v6
```

The v6 publisher requires an existing regular parent, rejects lexical symlink components before resolution, binds the parent and staged tree by directory descriptors and device/inode identities, fsyncs every file after its final `0444` chmod, validates the frozen private tree, and publishes with an atomic no-clobber rename followed by a parent fsync. Its descriptor ledger owns the parent, staging tree, and validator output descriptor from the instant each open returns, including before identity and target checks. It re-reads every frozen byte through the held tree descriptor and re-proves the parent and target identities before entering descriptor cleanup.

Every generated staging name is recorded before mkdir. Any `FileExistsError` is ambiguous because a wrapper may have created the entry before raising; v6 retains v5's fail-closed policy instead of retrying and reports the exact candidate path. On any acquisition or finalization failure, it attempts every acquired descriptor close, aggregates primary, recovery, and cleanup errors, reports the exact target and allocated staging paths, and does not return success. Regressions cover initial target-stat `EIO`, target-exists plus post-close `EIO`, validator acquisition identity failure plus post-close `EIO`, staging acquisition failure, create-then-`FileExistsError`, final real-close-then-raise for both held descriptors, descriptor-count stability, and two socket-blocked byte-exact fresh builds. The independent acceptance audit exercised seven acquisition, identity, create, and final-close failure scenarios; every intercepted open received a close attempt, descriptor growth was zero, and the complete v1-v6 mosaic lineage passed 67 tests offline with rasterio 1.5.0.

Failure recovery remains intentionally non-destructive. Portable POSIX `unlinkat` and `rmdir` select a victim by a mutable name; a prior inode check cannot close that check-to-use race. V6 therefore uses only atomic no-clobber renames during recovery. It reports observed or unprobeable staging, target, and generated quarantine paths, asserts writer ownership only after device/inode identity proof, parent-fsyncs successful recovery renames, and appends lookup, rollback, quarantine, restoration, sync, acquisition, and close errors after the primary failure. A failed build can leave a writer-owned recovery tree for later operator inspection and out-of-band cleanup; the publisher itself does not recursively delete it.
