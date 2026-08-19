# Local data

This directory contains ordinary, unencrypted files used by Data Center Atlas.
It is not a backup, has no credentials, and requires no restore or rehydration
tooling.

`external-captures/atlas-critical-v1-external-captures-2026-08-04/` contains
the retained historical capture package. Its 2,270 regular payload files are
checked by the package's `SHA256SUMS`. `MANIFEST.json` contains only the path
mapping used by historical validators; it contains no backup or encryption
metadata.

Generated release payloads remain in their canonical release, master, map, and
ledger directories rather than being duplicated here.
