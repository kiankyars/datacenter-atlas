# Data Center Atlas recovery

This directory contains only the encrypted recovery credential for the local
Kopia repository. It does not contain the repository password in plaintext or
any backed-up evidence payloads.

## Recovery anchors

- Kopia repository ID:
  `5b6ef7d3c48986ac012b1bc5f168f35c09a427a45ed60f7daadb647bd9295f85`
- Repository format: Kopia v3
- Content encryption: AES256-GCM-HMAC-SHA256
- Credential envelope: age, encrypted to the SSH public keys registered to the
  GitHub account at the time of creation
- Local repository path:
  `/Users/kian/Backups/datacenter-atlas/kopia-repository`
- Local config path:
  `/Users/kian/.config/kopia/datacenter-atlas.config`
- Critical snapshot tag: `purpose:critical-recovery`
- Critical snapshot pin: `critical-v1`
- Capture cutoff: `2026-07-24T22:51:19Z`

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

The restore test remains at
`/private/tmp/datacenter-atlas-restore-test-20260724` pending completion of the
off-site and external backup stages. It must not be treated as a backup.
