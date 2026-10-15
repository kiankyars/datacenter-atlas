"""Fail before deployment when the site or its GNU tar exceeds 1,000,000,000 bytes."""

import argparse
import json
from pathlib import Path
import tarfile

LIMIT_BYTES = 1_000_000_000


def measure(directory):
    total = 0
    archive = 1024  # Two terminal tar blocks, followed by record padding below.
    count = 0
    # The upload-pages-artifact action excludes hidden names. Counting them too is
    # conservative and avoids a guard that depends on shell glob behaviour.
    for path in [directory, *sorted(directory.rglob("*"))]:
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError(f"Pages output must contain only regular files and directories: {path}")
        relative = path.relative_to(directory).as_posix()
        info = tarfile.TarInfo("." if relative == "." else "./" + relative)
        if path.is_dir():
            info.type = tarfile.DIRTYPE
        else:
            info.size = path.stat().st_size
            total += info.size
            count += 1
        archive += len(info.tobuf(format=tarfile.GNU_FORMAT)) + ((info.size + 511) // 512) * 512
    archive = ((archive + 10239) // 10240) * 10240
    return {"file_bytes": total, "file_count": count, "gnu_tar_bytes_upper_bound": archive,
            "limit_bytes": LIMIT_BYTES, "remaining_bytes": LIMIT_BYTES - max(total, archive)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", required=True, type=Path)
    args = parser.parse_args(argv)
    report = measure(args.site.resolve())
    print(json.dumps(report, sort_keys=True))
    if report["remaining_bytes"] < 0:
        parser.exit(1, "Pages size limit exceeded; preserve existing downloads and change the publication plan.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
