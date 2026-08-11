# Atlas critical-v1 external captures

This package preserves the 60 critical-recovery snapshot roots that were outside the restored `/Users/kian/Developer/semiconductors` workspace: 55 roots formerly under `/Users/kian/.Trash` and 5 roots formerly under `/private/tmp`.

The package is ordinary filesystem data and does not require Kopia, the Kopia repository password, an age identity, or network access. Original absolute paths are represented below `payload/`; for example, `/private/tmp/example` is stored as `payload/private/tmp/example`.

## Package files

- `MANIFEST.json` is the canonical machine-readable provenance manifest. It records every original absolute path, Kopia snapshot manifest ID, root object ID, snapshot timestamps, and expected file, directory, symlink, and byte counts.
- `MANIFEST.tsv` is a tabular rendering of the same 60-root mapping.
- `VERIFICATION.tsv` compares expected and restored counts for every root. Every row must be `PASS`.
- `SHA256SUMS` contains a SHA-256 digest for each of the 2,270 regular payload files. From this directory, run `shasum -a 256 -c SHA256SUMS` to reread and verify them.
- `SYMLINKS.tsv` records the four preserved Chrome runtime symlinks and hashes each link-target string. These are historical metadata and can intentionally point to paths that no longer exist; no regular-file content depends on them.
- `METADATA-SHA256SUMS` verifies this README and the five manifest and verification files above. Run `shasum -a 256 -c METADATA-SHA256SUMS` from this directory.

The source Kopia objects were also checked with a targeted 100% file-content verification before export. The main semiconductors recovery was independently present at `/Users/kian/Developer/semiconductors` before the Downloads Atlas repository was removed.
