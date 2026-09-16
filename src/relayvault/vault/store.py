"""Linux snapshot publication, stable locks and encrypted recovery copies."""

from contextlib import contextmanager
import fcntl
import hashlib
import os
import re
from pathlib import Path
import stat
import tempfile

from relayvault import settings
from . import capsule as codec


class StorageError(ValueError):
    pass


class ConcurrentWriteError(StorageError):
    pass


class CommitUncertainError(StorageError):
    pass


def target_path(value):
    path = Path(value).expanduser().absolute()
    if "\0" in str(path):
        raise StorageError("Invalid path.")
    # A path alias must never bypass writer locks or redirect publication.
    for item in (path, *path.parents):
        if item.is_symlink():
            raise StorageError("Symlink paths are not supported.")
    return path.resolve()


def open_regular(path):
    path = target_path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise StorageError("Expected a regular file.")
        stream = os.fdopen(fd, "rb")
        fd = None
        return stream
    finally:
        if fd is not None:
            os.close(fd)


def identity(stream):
    info = os.fstat(stream.fileno())
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def temporary(directory):
    fd, name = tempfile.mkstemp(prefix=".relay-", suffix=".partial", dir=directory)
    path = Path(name)
    try:
        with os.fdopen(fd, "w+b") as stream:
            yield stream, path
    finally:
        path.unlink(missing_ok=True)


def publish(staged, destination, *, replace=False):
    if replace:
        os.replace(staged, destination)
    else:
        os.link(staged, destination, follow_symlinks=False)
    try:
        sync_directory(destination.parent)
    except OSError as error:
        raise CommitUncertainError(
            "Publication occurred but durability is uncertain; close and verify before further writes."
        ) from error


class Locks:
    def __init__(self):
        self.streams = []

    def acquire(self, label):
        directory = settings.private_directory(settings.home() / "locks")
        name = hashlib.sha256(label.encode()).hexdigest() + ".lock"
        fd = os.open(
            directory / name,
            os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK,
            0o600,
        )
        try:
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_nlink != 1
            ):
                raise StorageError("Invalid Relay lock file.")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ConcurrentWriteError(
                    "Another Relay session is using this vault."
                ) from error
            self.streams.append(fd)
            fd = None
        finally:
            if fd is not None:
                os.close(fd)

    def close(self):
        for fd in reversed(self.streams):
            os.close(fd)
        self.streams.clear()


def read_capsule(source, *, recovery=False):
    source.seek(0)
    signature = source.read(8)
    source.seek(0)
    if signature == codec.MAGIC:
        return codec.Capsule(source), False
    if signature == b"\x89PNG\r\n\x1a\n":
        from .png import capsule_stream

        return codec.Capsule(capsule_stream(source, recovery=recovery)), True
    raise codec.FormatError("No supported capsule or PNG carrier.")


def backup_capsule(capsule, key):
    capsule.verify(key)
    name = hashlib.sha256(capsule.header["vault_id"].encode()).hexdigest()
    directory = settings.private_directory(settings.home() / "backups" / name)
    snapshot = capsule.manifest
    destination = (
        directory
        / f"{snapshot['generation']:019d}-{snapshot['snapshot_id']}.relayvault"
    )
    if destination.exists() or destination.is_symlink():
        with open_regular(destination) as existing:
            candidate = codec.Capsule(existing)
            candidate.verify(key)
            if codec.digest(existing) != codec.digest(capsule.source):
                raise StorageError("Existing backup conflicts with this snapshot.")
            os.fsync(existing.fileno())
            sync_directory(directory)
        return destination
    with temporary(directory) as (stream, staged):
        codec.copy(capsule.source, stream)
        stream.flush()
        codec.Capsule(stream).verify(key)
        os.fsync(stream.fileno())
        publish(staged, destination)
    return destination


def prune_backups(vault_id):
    directory = (
        settings.home() / "backups" / hashlib.sha256(vault_id.encode()).hexdigest()
    )
    # Time of backup creation, not untrusted filenames/generation, defines retention.
    candidates = sorted(
        (
            p
            for p in directory.glob("*.relayvault")
            if re.fullmatch(r"[0-9]{19}-[0-9a-f]{32}\.relayvault", p.name)
        ),
        key=lambda p: p.lstat().st_mtime_ns,
        reverse=True,
    )
    for path in candidates[3:]:
        if stat.S_ISREG(path.lstat().st_mode):
            path.unlink()
    sync_directory(directory)


class Store:
    def __init__(self, path, *, recovery=False):
        self.path = target_path(path)
        self.locks = Locks()
        self.source = None
        self.recovery = recovery
        self.failed = False
        try:
            self.locks.acquire("path:" + str(self.path))
            self.source = open_regular(self.path)
            self.capsule, self.is_png = read_capsule(self.source, recovery=recovery)
            self.locks.acquire("vault:" + self.capsule.header["vault_id"])
            self.original_identity = identity(self.source)
            self.original_digest = codec.digest(self.source)
        except BaseException:
            self.close()
            raise

    def check_source(self):
        with open_regular(self.path) as stream:
            if (
                identity(stream) != self.original_identity
                or codec.digest(stream) != self.original_digest
            ):
                raise ConcurrentWriteError(
                    "Source changed externally; close and reopen."
                )

    def commit(self, key, records):
        if self.failed or self.recovery:
            raise StorageError("This source is read-only; export to a new path.")
        info = self.path.lstat()
        if info.st_uid != os.getuid() or info.st_nlink != 1:
            raise StorageError(
                "Writes require an owned file without hard-link aliases."
            )
        self.check_source()
        self.capsule.verify(key)
        backup_capsule(self.capsule, key)
        with temporary(self.path.parent) as (capsule_file, _):
            new = codec.write(
                capsule_file,
                self.capsule.header,
                key,
                records,
                generation=self.capsule.manifest["generation"] + 1,
            )
            with temporary(self.path.parent) as (output, staged):
                if self.is_png:
                    from .png import embed

                    embed(self.source, new.source, output, replace=True)
                else:
                    codec.copy(new.source, output)
                output.flush()
                read_capsule(output)[0].verify(key)
                os.fsync(output.fileno())
                self.check_source()
                try:
                    publish(staged, self.path, replace=True)
                except CommitUncertainError:
                    self.failed = True
                    raise
        try:
            replacement = open_regular(self.path)
            try:
                opened, png = read_capsule(replacement)
                opened.verify(key)
            except BaseException:
                replacement.close()
                raise
            self.source.close()
            self.source = replacement
            self.capsule = opened
            self.original_identity = identity(self.source)
            self.original_digest = codec.digest(self.source)
        except BaseException:
            self.failed = True
            raise
        # Retention failure cannot undo a successful commit; retain extra copies.
        try:
            prune_backups(self.capsule.header["vault_id"])
        except OSError:
            pass
        return self.capsule.manifest

    def export(self, key, destination, *, image=None):
        destination = target_path(destination)
        if destination.exists() or destination.is_symlink():
            raise StorageError("Destination already exists.")
        self.locks.acquire("path:" + str(destination))
        self.check_source()
        backup_capsule(self.capsule, key)
        with temporary(destination.parent) as (output, staged):
            if image is None:
                codec.copy(self.capsule.source, output)
            else:
                from .png import embed

                with open_regular(image) as original:
                    embed(original, self.capsule.source, output)
            output.flush()
            read_capsule(output)[0].verify(key)
            os.fsync(output.fileno())
            self.check_source()
            publish(staged, destination)
        return destination

    def close(self):
        if self.source is not None:
            self.source.close()
            self.source = None
        self.locks.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def create(
    destination,
    header,
    key,
    records=(),
    *,
    image=None,
    generation=1,
    locks=None,
    check_source=None,
):
    destination = target_path(destination)
    if destination.exists() or destination.is_symlink():
        raise StorageError("Destination already exists.")
    owned = locks is None
    locks = Locks() if owned else locks
    try:
        locks.acquire("path:" + str(destination))
        if owned:
            locks.acquire("vault:" + header["vault_id"])
        with temporary(destination.parent) as (capsule_file, _):
            new = codec.write(capsule_file, header, key, records, generation=generation)
            backup_capsule(new, key)
            with temporary(destination.parent) as (output, staged):
                if image is not None:
                    from .png import embed

                    with open_regular(image) as original:
                        embed(original, new.source, output)
                else:
                    codec.copy(new.source, output)
                output.flush()
                read_capsule(output)[0].verify(key)
                os.fsync(output.fileno())
                if check_source is not None:
                    check_source()
                publish(staged, destination)
    finally:
        if owned:
            locks.close()
    return destination
