"""Explicit authenticated copy from closed V1/V2 directories; never writes source."""

from contextlib import ExitStack
from dataclasses import asdict
from .legacy import config as legacy
from .legacy.storage import VaultEntry, VaultManifest, _validate_manifest
from .vault import capsule, crypto, store


def migrate(source, destination, password, *, image=None):
    source = store.target_path(source)
    if store.settings.home().resolve().is_relative_to(source):
        raise store.StorageError(
            "Set RELAY_HOME outside the legacy source before migration."
        )
    paths = legacy.resolve_paths(source)
    tracked = []
    with ExitStack() as stack:

        def track(path, limit=None):
            stream = stack.enter_context(store.open_regular(path))
            before = store.identity(stream)
            if limit is not None and before[2] > limit:
                raise store.StorageError("Legacy metadata exceeds size limit.")
            tracked.append((path, before, capsule.digest(stream)))
            return stream

        config_stream = track(paths.config_path, capsule.MAX_HEADER)
        config = legacy.validate_config(capsule.decode(config_stream.read()))
        legacy.validate_initialized_config(config)
        key = bytearray(crypto.derive_master_key(password, config.kdf))
        del password
        try:
            crypto.verify_key_check(bytes(key), config.vault_id, config.key_check)
            manifest_stream = track(paths.manifest_path, capsule.MAX_MANIFEST)
            plain = crypto.decrypt_bytes(
                manifest_stream.read(),
                bytes(key),
                crypto.build_aad(config.vault_id, crypto.MANIFEST),
                crypto.MANIFEST,
            )
            data = capsule.decode(plain)
            if (
                not isinstance(data, dict)
                or set(data) != {"version", "entries"}
                or data["version"] != 1
                or type(data["version"]) is not int
                or not isinstance(data["entries"], list)
                or len(data["entries"]) > capsule.MAX_ENTRIES
            ):
                raise store.StorageError("Invalid legacy manifest.")
            try:
                manifest = VaultManifest(1, [VaultEntry(**e) for e in data["entries"]])
                _validate_manifest(manifest)
            except (ValueError, TypeError) as error:
                raise store.StorageError("Invalid legacy entries.") from error
            records = []
            for entry in manifest.entries:
                stream = track(paths.objects_dir / f"{entry.id}.vlt")
                if (
                    crypto.verify_stream(
                        stream,
                        bytes(key),
                        crypto.build_aad(config.vault_id, crypto.FILE, entry.id),
                        crypto.FILE,
                    )
                    != entry.size
                ):
                    raise crypto.IntegrityError("Legacy object size mismatch.")
                records.append((asdict(entry), stream))

            def check():
                for path, before, checksum in tracked:
                    with store.open_regular(path) as current:
                        if (
                            store.identity(current) != before
                            or capsule.digest(current) != checksum
                        ):
                            raise store.ConcurrentWriteError(
                                "Legacy source changed; close its writer and retry."
                            )

            check()
            header = {
                k: getattr(config, k)
                for k in ("vault_id", "kdf", "encryption", "key_check")
            }
            result = store.create(
                destination,
                header,
                bytes(key),
                records,
                image=image,
                check_source=check,
            )
            check()
            with store.open_regular(result) as written:
                store.read_capsule(written)[0].verify(bytes(key))
            referenced = {f"{e.id}.vlt" for e in manifest.entries}
            orphans = sum(
                1 for p in paths.objects_dir.iterdir() if p.name not in referenced
            )
            return result, orphans
        finally:
            key[:] = bytes(len(key))
