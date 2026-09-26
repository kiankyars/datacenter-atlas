"""Descriptor-bound publication primitives for the v32 master/map pair.

The helpers in this module are deliberately small and artifact-agnostic.  They
bind every namespace parent by descriptor, inventory every bundle inode, use
atomic no-replace renames in both directions, and keep enough identity
information to roll back only artifacts created by the current publisher.
"""

from __future__ import annotations

import ctypes
import errno
import os
import stat
import sys
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TypeAlias

ErrorFactory: TypeAlias = Callable[[str], Exception]
Identity: TypeAlias = tuple[int, int]
NodeIdentity: TypeAlias = tuple[str, int, int]
TreeIdentity: TypeAlias = dict[str, NodeIdentity]

_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_TIME_EPSILON = 0.000_001


@dataclass(frozen=True)
class ParentBinding:
    """A lexical directory path bound to one open directory inode."""

    path: Path
    descriptor: int
    identity: Identity


ParentBindings: TypeAlias = Mapping[Path, ParentBinding]


def _absolute(path: str | Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _identity(metadata: os.stat_result) -> Identity:
    return metadata.st_dev, metadata.st_ino


def _node_identity(metadata: os.stat_result) -> NodeIdentity:
    mode = metadata.st_mode
    if stat.S_ISDIR(mode):
        kind = "directory"
    elif stat.S_ISREG(mode):
        kind = "file"
    else:
        kind = "unsafe"
    return kind, metadata.st_dev, metadata.st_ino


def _component(name: str, *, label: str, error: ErrorFactory) -> str:
    if (
        not name
        or name in {".", ".."}
        or os.sep in name
        or (os.altsep is not None and os.altsep in name)
    ):
        raise error(f"{label} is not one path component: {name!r}")
    return name


def _binding(
    bindings: ParentBindings,
    parent: str | Path,
    *,
    error: ErrorFactory,
) -> ParentBinding:
    key = _absolute(parent)
    try:
        return bindings[key]
    except KeyError as cause:
        raise error(f"publication parent is not descriptor-bound: {key}") from cause


def _open_parent(path: Path, *, error: ErrorFactory) -> ParentBinding:
    try:
        lexical = path.lstat()
    except OSError as cause:
        raise error(f"cannot inspect publication parent: {path}") from cause
    if stat.S_ISLNK(lexical.st_mode) or not stat.S_ISDIR(lexical.st_mode):
        raise error(f"publication parent is not a regular directory: {path}")
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | _DIRECTORY | _NOFOLLOW | _CLOEXEC,
        )
    except OSError as cause:
        raise error(f"cannot bind publication parent: {path}") from cause
    observed = os.fstat(descriptor)
    if _identity(observed) != _identity(lexical) or not stat.S_ISDIR(
        observed.st_mode
    ):
        os.close(descriptor)
        raise error(f"publication parent changed while binding: {path}")
    return ParentBinding(path, descriptor, _identity(observed))


@contextmanager
def bound_parents(
    parents: Iterable[str | Path],
    *,
    error: ErrorFactory,
) -> Iterator[dict[Path, ParentBinding]]:
    """Bind unique lexical parents until all publication work has completed."""

    bindings: dict[Path, ParentBinding] = {}
    try:
        for candidate in parents:
            path = _absolute(candidate)
            if path not in bindings:
                bindings[path] = _open_parent(path, error=error)
        assert_parent_bindings(bindings, error=error, label="initial binding")
        yield bindings
    finally:
        for binding in reversed(tuple(bindings.values())):
            os.close(binding.descriptor)


def assert_parent_bindings(
    bindings: ParentBindings,
    *,
    error: ErrorFactory,
    label: str,
) -> None:
    for binding in bindings.values():
        descriptor_metadata = os.fstat(binding.descriptor)
        if (
            _identity(descriptor_metadata) != binding.identity
            or not stat.S_ISDIR(descriptor_metadata.st_mode)
        ):
            raise error(f"{label}: bound parent descriptor changed: {binding.path}")
        try:
            lexical = binding.path.lstat()
        except OSError as cause:
            raise error(f"{label}: bound parent path vanished: {binding.path}") from cause
        if (
            stat.S_ISLNK(lexical.st_mode)
            or not stat.S_ISDIR(lexical.st_mode)
            or _identity(lexical) != binding.identity
        ):
            raise error(f"{label}: bound parent path was swapped: {binding.path}")


def add_parent_binding(
    bindings: dict[Path, ParentBinding],
    parent: str | Path,
    *,
    error: ErrorFactory,
) -> ParentBinding:
    """Extend a live binding set, keeping the new descriptor in its cleanup scope."""

    path = _absolute(parent)
    if path not in bindings:
        bindings[path] = _open_parent(path, error=error)
    assert_parent_bindings(bindings, error=error, label="extended binding")
    return bindings[path]


def entry_present(
    path: str | Path,
    bindings: ParentBindings,
    *,
    error: ErrorFactory,
) -> bool:
    candidate = _absolute(path)
    binding = _binding(bindings, candidate.parent, error=error)
    try:
        os.stat(candidate.name, dir_fd=binding.descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return True


def entry_identity(
    path: str | Path,
    bindings: ParentBindings,
    *,
    directory: bool,
    error: ErrorFactory,
) -> Identity:
    candidate = _absolute(path)
    binding = _binding(bindings, candidate.parent, error=error)
    name = _component(candidate.name, label="artifact name", error=error)
    try:
        metadata = os.stat(name, dir_fd=binding.descriptor, follow_symlinks=False)
    except OSError as cause:
        raise error(f"cannot inspect publication artifact: {candidate}") from cause
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(metadata.st_mode):
        raise error(f"publication artifact has unsafe type: {candidate}")
    return _identity(metadata)


def has_identity(
    path: str | Path,
    identity: Identity,
    bindings: ParentBindings,
    *,
    directory: bool,
    error: ErrorFactory,
) -> bool:
    try:
        return (
            entry_identity(
                path,
                bindings,
                directory=directory,
                error=error,
            )
            == identity
        )
    except Exception as cause:  # noqa: BLE001 - false is the safe ownership answer
        if isinstance(cause, OSError):
            return False
        try:
            return not entry_present(path, bindings, error=error) and False
        except Exception:  # noqa: BLE001 - caller reports the primary boundary error
            return False


def _open_bound_entry(
    path: Path,
    bindings: ParentBindings,
    *,
    directory: bool,
    error: ErrorFactory,
) -> tuple[int, ParentBinding]:
    binding = _binding(bindings, path.parent, error=error)
    flags = os.O_RDONLY | _NOFOLLOW | _CLOEXEC
    if directory:
        flags |= _DIRECTORY
    try:
        descriptor = os.open(path.name, flags, dir_fd=binding.descriptor)
    except OSError as cause:
        raise error(f"cannot open bound publication artifact: {path}") from cause
    metadata = os.fstat(descriptor)
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(metadata.st_mode):
        os.close(descriptor)
        raise error(f"bound publication artifact has unsafe type: {path}")
    return descriptor, binding


def _scan_directory(
    descriptor: int,
    prefix: str,
    *,
    error: ErrorFactory,
) -> dict[str, tuple[NodeIdentity, os.stat_result]]:
    result: dict[str, tuple[NodeIdentity, os.stat_result]] = {}
    try:
        names = sorted(os.listdir(descriptor))
    except OSError as cause:
        raise error(f"cannot enumerate publication bundle: {prefix or '.'}") from cause
    for name in names:
        _component(name, label="bundle member", error=error)
        relative = f"{prefix}/{name}" if prefix else name
        try:
            metadata = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        except OSError as cause:
            raise error(f"cannot inspect publication bundle member: {relative}") from cause
        identity = _node_identity(metadata)
        if identity[0] == "unsafe":
            raise error(f"publication bundle member has unsafe type: {relative}")
        result[relative] = identity, metadata
        if identity[0] == "directory":
            try:
                child = os.open(
                    name,
                    os.O_RDONLY | _DIRECTORY | _NOFOLLOW | _CLOEXEC,
                    dir_fd=descriptor,
                )
            except OSError as cause:
                raise error(
                    f"cannot bind publication bundle directory: {relative}"
                ) from cause
            try:
                if _identity(os.fstat(child)) != (identity[1], identity[2]):
                    raise error(
                        f"publication bundle directory changed: {relative}"
                    )
                result.update(_scan_directory(child, relative, error=error))
            finally:
                os.close(child)
    return result


def tree_inventory(
    bundle: str | Path,
    bindings: ParentBindings,
    *,
    error: ErrorFactory,
) -> TreeIdentity:
    root = _absolute(bundle)
    descriptor, _binding_value = _open_bound_entry(
        root,
        bindings,
        directory=True,
        error=error,
    )
    try:
        root_metadata = os.fstat(descriptor)
        scanned = _scan_directory(descriptor, "", error=error)
    finally:
        os.close(descriptor)
    return {
        ".": _node_identity(root_metadata),
        **{name: value[0] for name, value in scanned.items()},
    }


def assert_tree_identity(
    bundle: str | Path,
    expected: Mapping[str, NodeIdentity],
    bindings: ParentBindings,
    *,
    error: ErrorFactory,
    label: str,
) -> None:
    observed = tree_inventory(bundle, bindings, error=error)
    if observed != dict(expected):
        raise error(f"{label}: recursive bundle identity changed")


def _rename_noreplace_at(
    source_binding: ParentBinding,
    source_name: str,
    destination_binding: ParentBinding,
    destination_name: str,
    *,
    error: ErrorFactory,
) -> None:
    source = os.fsencode(_component(source_name, label="rename source", error=error))
    destination = os.fsencode(
        _component(destination_name, label="rename destination", error=error)
    )
    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        function = getattr(library, "renameatx_np", None)
        flag = 0x00000004
    elif sys.platform.startswith("linux"):
        function = getattr(library, "renameat2", None)
        flag = 0x00000001
    else:  # pragma: no cover - supported release hosts are Darwin/Linux
        function = None
        flag = 0
    if function is None:  # pragma: no cover - fail closed on unsupported libc
        raise error("descriptor-bound atomic no-replace rename is unavailable")
    function.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    function.restype = ctypes.c_int
    result = function(
        source_binding.descriptor,
        source,
        destination_binding.descriptor,
        destination,
        flag,
    )
    if result == 0:
        os.fsync(source_binding.descriptor)
        if destination_binding.descriptor != source_binding.descriptor:
            os.fsync(destination_binding.descriptor)
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise error(
            "late output collision; refusing overwrite: "
            f"{destination_binding.path / destination_name}"
        )
    raise error(
        "descriptor-bound atomic no-replace rename failed: "
        f"{source_binding.path / source_name} -> "
        f"{destination_binding.path / destination_name}: "
        f"{os.strerror(error_number)}"
    )


def promote_noreplace(
    stage: str | Path,
    destination: str | Path,
    bindings: ParentBindings,
    *,
    directory: bool,
    error: ErrorFactory,
) -> Identity:
    source = _absolute(stage)
    target = _absolute(destination)
    assert_parent_bindings(bindings, error=error, label="before promotion")
    identity = entry_identity(
        source,
        bindings,
        directory=directory,
        error=error,
    )
    if entry_present(target, bindings, error=error):
        raise error(f"final path collision; refusing overwrite: {target}")
    source_binding = _binding(bindings, source.parent, error=error)
    destination_binding = _binding(bindings, target.parent, error=error)
    _rename_noreplace_at(
        source_binding,
        source.name,
        destination_binding,
        target.name,
        error=error,
    )
    if not has_identity(
        target,
        identity,
        bindings,
        directory=directory,
        error=error,
    ):
        raise error(f"promoted artifact identity differs: {target}")
    assert_parent_bindings(bindings, error=error, label="after promotion")
    return identity


def rollback_noreplace(
    destination: str | Path,
    stage: str | Path,
    identity: Identity,
    bindings: ParentBindings,
    *,
    directory: bool,
    error: ErrorFactory,
) -> None:
    source = _absolute(destination)
    target = _absolute(stage)
    assert_parent_bindings(bindings, error=error, label="before rollback")
    if not has_identity(
        source,
        identity,
        bindings,
        directory=directory,
        error=error,
    ):
        raise error(f"refusing identity-mismatched rollback: {source}")
    if entry_present(target, bindings, error=error):
        raise error(f"rollback stage is occupied: {target}")
    source_binding = _binding(bindings, source.parent, error=error)
    target_binding = _binding(bindings, target.parent, error=error)
    _rename_noreplace_at(
        source_binding,
        source.name,
        target_binding,
        target.name,
        error=error,
    )
    if not has_identity(
        target,
        identity,
        bindings,
        directory=directory,
        error=error,
    ):
        raise error(f"rolled-back artifact identity differs: {target}")
    assert_parent_bindings(bindings, error=error, label="after rollback")


def rollback_owned_final(
    operation_error: BaseException,
    *,
    destination: str | Path,
    stage: str | Path,
    identity: Identity,
    bindings: ParentBindings,
    directory: bool,
    error: ErrorFactory,
) -> bool:
    """Return whether a final path remains after the rollback attempt."""

    if has_identity(
        destination,
        identity,
        bindings,
        directory=directory,
        error=error,
    ):
        try:
            if directory:
                make_directory_renameable(
                    destination,
                    identity,
                    bindings,
                    error=error,
                )
            rollback_noreplace(
                destination,
                stage,
                identity,
                bindings,
                directory=directory,
                error=error,
            )
            if directory:
                freeze_directory(
                    stage,
                    identity,
                    bindings,
                    error=error,
                )
        except Exception as rollback_error:  # noqa: BLE001 - preserve primary failure
            destination_remains = has_identity(
                destination,
                identity,
                bindings,
                directory=directory,
                error=error,
            )
            if directory and destination_remains:
                try:
                    freeze_directory(
                        destination,
                        identity,
                        bindings,
                        error=error,
                    )
                except Exception as freeze_error:  # noqa: BLE001
                    rollback_error.add_note(
                        f"publication rollback refreeze failed: {freeze_error}"
                    )
            operation_error.add_note(f"publication rollback failed: {rollback_error}")
            if destination_remains:
                return True
            try:
                return entry_present(destination, bindings, error=error)
            except Exception as inspection_error:  # noqa: BLE001
                operation_error.add_note(
                    "cannot inspect final after rollback failure: "
                    f"{inspection_error}"
                )
                return True
        return False
    try:
        if entry_present(destination, bindings, error=error):
            operation_error.add_note(
                f"refusing rollback of substituted final: {destination}"
            )
            return True
    except Exception as inspection_error:  # noqa: BLE001
        operation_error.add_note(
            f"cannot inspect final during rollback: {inspection_error}"
        )
        return True
    return False


def _refresh_directory(
    descriptor: int,
    prefix: str,
    expected: Mapping[str, NodeIdentity],
    *,
    error: ErrorFactory,
) -> None:
    names = sorted(os.listdir(descriptor))
    expected_names = {
        relative.removeprefix(f"{prefix}/").split("/", 1)[0]
        if prefix
        else relative.split("/", 1)[0]
        for relative in expected
        if relative != "."
        and (not prefix or relative.startswith(f"{prefix}/"))
    }
    if set(names) != expected_names:
        raise error(f"recursive bundle changed before ctime refresh: {prefix or '.'}")
    for name in names:
        relative = f"{prefix}/{name}" if prefix else name
        node = expected.get(relative)
        if node is None:
            raise error(f"unexpected bundle member before ctime refresh: {relative}")
        flags = os.O_RDONLY | _NOFOLLOW | _CLOEXEC
        if node[0] == "directory":
            flags |= _DIRECTORY
        try:
            child = os.open(name, flags, dir_fd=descriptor)
        except OSError as cause:
            raise error(f"cannot open bundle member for ctime refresh: {relative}") from cause
        try:
            metadata = os.fstat(child)
            if _node_identity(metadata) != node:
                raise error(f"bundle member changed before ctime refresh: {relative}")
            if node[0] == "directory":
                _refresh_directory(child, relative, expected, error=error)
                os.fchmod(child, 0o500)
                os.fchmod(child, 0o555)
            else:
                os.fchmod(child, 0o400)
                os.fchmod(child, 0o444)
            os.fsync(child)
        finally:
            os.close(child)


def refresh_publication_ctimes(
    definition: str | Path,
    definition_identity: Identity,
    bundle: str | Path,
    bundle_identity: Mapping[str, NodeIdentity],
    bindings: ParentBindings,
    *,
    target: datetime,
    error: ErrorFactory,
) -> None:
    if datetime.now(target.tzinfo) < target:
        raise error("cannot refresh publication ctimes before declared time")
    definition_path = _absolute(definition)
    descriptor, _definition_binding = _open_bound_entry(
        definition_path,
        bindings,
        directory=False,
        error=error,
    )
    try:
        if _identity(os.fstat(descriptor)) != definition_identity:
            raise error("definition changed before ctime refresh")
        os.fchmod(descriptor, 0o400)
        os.fchmod(descriptor, 0o444)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)

    bundle_path = _absolute(bundle)
    root, _bundle_binding = _open_bound_entry(
        bundle_path,
        bindings,
        directory=True,
        error=error,
    )
    try:
        if _node_identity(os.fstat(root)) != bundle_identity.get("."):
            raise error("bundle root changed before ctime refresh")
        _refresh_directory(root, "", bundle_identity, error=error)
        os.fchmod(root, 0o500)
        os.fchmod(root, 0o555)
        os.fsync(root)
    finally:
        os.close(root)
    assert_parent_bindings(bindings, error=error, label="after ctime refresh")


def make_directory_renameable(
    bundle: str | Path,
    identity: Identity,
    bindings: ParentBindings,
    *,
    error: ErrorFactory,
) -> None:
    path = _absolute(bundle)
    descriptor, _binding_value = _open_bound_entry(
        path,
        bindings,
        directory=True,
        error=error,
    )
    try:
        if _identity(os.fstat(descriptor)) != identity:
            raise error(f"bundle root changed before promotion: {path}")
        os.fchmod(descriptor, 0o755)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def freeze_directory(
    bundle: str | Path,
    identity: Identity,
    bindings: ParentBindings,
    *,
    error: ErrorFactory,
) -> None:
    path = _absolute(bundle)
    descriptor, _binding_value = _open_bound_entry(
        path,
        bindings,
        directory=True,
        error=error,
    )
    try:
        if _identity(os.fstat(descriptor)) != identity:
            raise error(f"bundle root changed before refreeze: {path}")
        os.fchmod(descriptor, 0o555)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _timestamped_stats(
    definition: Path,
    definition_identity: Identity,
    bundle: Path,
    bundle_identity: Mapping[str, NodeIdentity],
    bindings: ParentBindings,
    *,
    error: ErrorFactory,
) -> dict[str, os.stat_result]:
    definition_descriptor, _definition_binding = _open_bound_entry(
        definition,
        bindings,
        directory=False,
        error=error,
    )
    try:
        definition_metadata = os.fstat(definition_descriptor)
        if _identity(definition_metadata) != definition_identity:
            raise error("definition identity changed during temporal validation")
    finally:
        os.close(definition_descriptor)
    bundle_descriptor, _bundle_binding = _open_bound_entry(
        bundle,
        bindings,
        directory=True,
        error=error,
    )
    try:
        bundle_metadata = os.fstat(bundle_descriptor)
        scanned = _scan_directory(bundle_descriptor, "", error=error)
        observed_tree = {
            ".": _node_identity(bundle_metadata),
            **{name: value[0] for name, value in scanned.items()},
        }
        if observed_tree != dict(bundle_identity):
            raise error("recursive bundle identity changed during temporal validation")
    finally:
        os.close(bundle_descriptor)
    return {
        "definition": definition_metadata,
        "bundle/.": bundle_metadata,
        **{f"bundle/{name}": value[1] for name, value in scanned.items()},
    }


def validate_publication_times(
    definition: str | Path,
    definition_identity: Identity,
    bundle: str | Path,
    bundle_identity: Mapping[str, NodeIdentity],
    bindings: ParentBindings,
    *,
    target: datetime,
    wall_clock: datetime,
    require_live: bool,
    error: ErrorFactory,
) -> None:
    definition_path = _absolute(definition)
    bundle_path = _absolute(bundle)
    if require_live and wall_clock < target:
        raise error("declared publication time exceeds validation wall clock")
    target_epoch = target.timestamp()
    wall_epoch = wall_clock.timestamp()
    for label, metadata in _timestamped_stats(
        definition_path,
        definition_identity,
        bundle_path,
        bundle_identity,
        bindings,
        error=error,
    ).items():
        birth = getattr(metadata, "st_birthtime", metadata.st_mtime)
        if max(birth, metadata.st_mtime) > target_epoch + _TIME_EPSILON:
            raise error(f"inode birth/mtime post-dates declared time: {label}")
        if require_live and metadata.st_ctime + _TIME_EPSILON < target_epoch:
            raise error(f"recursive ctime predates declared time: {label}")
        if require_live and metadata.st_ctime > wall_epoch + _TIME_EPSILON:
            raise error(f"recursive ctime exceeds validation wall clock: {label}")


@contextmanager
def publication_lock(
    lock_path: str | Path,
    bindings: ParentBindings,
    *,
    error: ErrorFactory,
    completion_check: Callable[[], None] | None = None,
) -> Iterator[None]:
    path = _absolute(lock_path)
    binding = _binding(bindings, path.parent, error=error)
    name = _component(path.name, label="publication lock", error=error)
    try:
        descriptor = os.open(
            name,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | _NOFOLLOW | _CLOEXEC,
            0o600,
            dir_fd=binding.descriptor,
        )
    except FileExistsError as cause:
        raise error(f"active publication lock exists: {path}") from cause
    lock_identity = _identity(os.fstat(descriptor))
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        os.fsync(binding.descriptor)
        yield
    finally:
        active_error = sys.exception()
        try:
            if not has_identity(
                path,
                lock_identity,
                bindings,
                directory=False,
                error=error,
            ):
                raise error(f"publication lock was substituted: {path}")
            os.unlink(name, dir_fd=binding.descriptor)
            os.fsync(binding.descriptor)
            assert_parent_bindings(
                bindings,
                error=error,
                label="publication lock cleanup",
            )
            if active_error is None and completion_check is not None:
                completion_check()
        except Exception as cleanup_error:
            if active_error is None:
                raise
            active_error.add_note(f"publication lock cleanup failed: {cleanup_error}")
        finally:
            os.close(descriptor)
