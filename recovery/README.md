# Data Center Atlas recovery

This directory tracks the encrypted Kopia credential and the small provenance
envelope for the portable external-capture package. It does not contain the
repository password in plaintext. Kopia blobs and the external-capture payload
are intentionally not committed to Git.

## Recovery anchors

- Kopia repository ID:
  `5b6ef7d3c48986ac012b1bc5f168f35c09a427a45ed60f7daadb647bd9295f85`
- Repository format: Kopia v3
- Content encryption: AES256-GCM-HMAC-SHA256
- Credential envelope: age, encrypted to the SSH public keys registered to the
  GitHub account at the time of creation
- Current local repository location:
  `/Users/kian/Backups/datacenter-atlas/kopia-repository-v1`
- Repository checksum manifest:
  `/Users/kian/Backups/datacenter-atlas/kopia-repository-v1.SHA256SUMS`
- Full-workspace snapshot ID:
  `5a29490e6b97a11d17855053f2de4b90`
- Full-workspace root object:
  `k5b47d38ce9389e6eeb53d96265a11da7`
- Preserved publication-hardening branch:
  `wip/v32-publication-hardening-20260724` at
  `217716652759e67ed685f1fe1a6754c337d55c31`
- Critical snapshot tag: `purpose:critical-recovery`
- Critical snapshot pin: `critical-v1`
- Capture cutoff: `2026-07-24T22:51:19Z`

The filesystem path is a machine-local convenience, not the repository's
identity. On 2026-08-18 all 4,310 regular repository files were hydrated and
hashed before a same-volume move out of iCloud. The checksum manifest above has
SHA-256 `87ed0ead18a1e593985fe762cf4a5ab86b110ab193911c20831dbea65ce87bf4`.
A read-only reconnect at the new path confirmed the repository ID and the
full-workspace snapshot above.

On 2026-08-10 a read-only audit found 369 pinned snapshots, 4,309 blobs
occupying approximately 102.6 GB, 215,128,363,129 logical bytes, 416,933 files,
and zero content errors. The full-workspace snapshot records the former
`/Users/kian/Developer/semiconductors` tree: 205,645,209,106 logical bytes,
367,591 files, 214,671 directories, and zero errors. Use the repository and
snapshot IDs to identify the archive after any later move.

The first critical set contains 368 pinned snapshots: 9,483,154,023 logical
bytes, 49,299 files, 10,273 directories, four symlinks, and zero read failures.
Its local encrypted repository occupied approximately 3.91 GiB after
compression and deduplication.

## Credential recovery

From a machine that has one of the corresponding SSH private keys:

```sh
age --decrypt \
  --identity ~/.ssh/id_ed25519 \
  recovery/kopia-repository-password.age
```

Provide the resulting password directly to Kopia. Do not save it in this Git
repository, shell history, logs, or a plaintext configuration file.

After retrieving the Kopia repository from off-site storage, connect to its
filesystem root:

```sh
kopia repository connect filesystem \
  --path /path/to/kopia-repository \
  --config-file /path/to/datacenter-atlas.config
```

Then inspect and restore:

```sh
kopia repository status --config-file=/path/to/datacenter-atlas.config
kopia snapshot list --all --config-file=/path/to/datacenter-atlas.config
kopia snapshot restore OBJECT_ID /path/to/empty-restore-target \
  --config-file=/path/to/datacenter-atlas.config \
  --no-progress --write-files-atomically
```

## Verified restore, 2026-07-24

A separate restore reconstructed 2,090 files, 448 directories, and four
symlinks across five representative snapshot roots (1.26 GB restored).
Checksum-mode comparisons against the live originals found no content, path,
deletion, or symlink differences. Seven large files totaling approximately
1.00 GB also matched independent SHA-256 calculations.

The disposable restore target was removed after verification. It was never a
backup.

## Recovery order

1. Restore Git history from the public remote, including the WIP branch above.
2. Use the tracked release manifests to identify and validate ignored release
   payloads.
3. Restore missing workspace payloads from the full-workspace Kopia snapshot.
4. Use the portable package below for the 60 historical roots that lived
   outside the workspace.

## Portable external captures

The 60 `critical-v1` snapshot roots that originally lived outside the
Semiconductors workspace are installed at
`recovery/external-captures/atlas-critical-v1-external-captures-2026-08-04/`.
Their original absolute paths are retained in the package manifest and in
frozen Atlas provenance. Runtime readers use
`datacenter_atlas.external_captures.resolve_external_capture` to map those
historical paths to the local payload without recreating old Trash or
`/private/tmp` locations.

Only the package's README, manifests, verification tables, and checksum files
are versioned. The 465 MiB `payload/` tree remains ignored and local-only. A
portable copy may live elsewhere by setting
`DATACENTER_ATLAS_EXTERNAL_CAPTURES_ROOT` to the package directory.

From the package directory, verify the ordinary files and metadata with:

```sh
shasum -a 256 -c SHA256SUMS
shasum -a 256 -c METADATA-SHA256SUMS
```

`SYMLINKS.tsv` records four intentionally historical Chrome runtime symlinks.
Verify their link-target strings; do not dereference or launch the quarantined
Chrome profile.
