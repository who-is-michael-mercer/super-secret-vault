import io
import hashlib
import struct
import uuid
from datetime import datetime, timezone
import pytest
from relayvault.vault import capsule as c, crypto


@pytest.fixture
def material():
    header, key = c.metadata("capsule-password")
    yield header, bytes(key)
    key[:] = bytes(len(key))


def records(header, key, count=1):
    now = datetime.now(timezone.utc).isoformat()
    result = []
    for i in range(count):
        identity = uuid.uuid4().hex
        blob = crypto.encrypt_bytes(
            b"secret content",
            key,
            crypto.build_aad(header["vault_id"], crypto.FILE, identity),
            crypto.FILE,
        )
        result.append(
            (
                dict(
                    id=identity,
                    name=f"secret-name-{i}",
                    size=14,
                    created_at=now,
                    updated_at=now,
                ),
                io.BytesIO(blob),
            )
        )
    return result


def snapshot(material, count=1):
    header, key = material
    output = io.BytesIO()
    c.write(output, header, key, records(header, key, count))
    return output


def test_portable_roundtrip_and_wrong_password(material):
    output = snapshot(material)
    assert (
        b"secret content" not in output.getvalue()
        and b"secret-name" not in output.getvalue()
    )
    opened = c.Capsule(output)
    key = opened.authenticate("capsule-password")
    assert opened.verify(bytes(key))["entries"][0]["name"] == "secret-name-0"
    with pytest.raises(crypto.IntegrityError):
        c.Capsule(output).authenticate("wrong")


@pytest.mark.parametrize(
    "mutation", ["footer", "header", "truncate", "trailing", "huge", "manifest"]
)
def test_framing_damage(material, mutation):
    data = bytearray(snapshot(material).getvalue())
    if mutation == "truncate":
        data = data[:-1]
    elif mutation == "trailing":
        data += b"x"
    elif mutation == "huge":
        data[8:12] = struct.pack(">I", 2**32 - 1)
    else:
        data[{"footer": -1, "header": 25, "manifest": 700}[mutation]] ^= 1
    with pytest.raises((ValueError, crypto.VaultFormatError)):
        c.Capsule(io.BytesIO(data))


def test_authenticated_manifest_binds_ciphertext_even_if_footer_recomputed(material):
    data = bytearray(snapshot(material).getvalue())
    opened = c.Capsule(io.BytesIO(data))
    data[opened.objects_offset + 20] ^= 1
    data[-32:] = hashlib.sha256(data[: -c.FOOTER.size]).digest()
    opened = c.Capsule(io.BytesIO(data))
    opened.unlock(material[1])
    with pytest.raises(crypto.IntegrityError):
        opened.verify(material[1])


def test_bounded_record_never_reads_next_object(material):
    output = snapshot(material, 2)
    opened = c.Capsule(output)
    opened.verify(material[1])
    entry = opened.manifest["entries"][0]
    stream = opened.record(entry)
    assert len(stream.read()) == entry["length"] and stream.read() == b""
    with pytest.raises(c.FormatError):
        stream.seek(entry["length"] + 1)


def test_copy_records_preserves_ciphertext_fresh_manifest(material):
    first = c.Capsule(snapshot(material))
    first.unlock(material[1])
    out = io.BytesIO()
    second = c.write(
        out,
        first.header,
        material[1],
        [(e, first.record(e)) for e in first.manifest["entries"]],
        generation=2,
    )
    assert (
        second.record(second.manifest["entries"][0]).read()
        == first.record(first.manifest["entries"][0]).read()
    )
    first.manifest_record.seek(0)
    second.manifest_record.seek(0)
    assert first.manifest_record.read() != second.manifest_record.read()
    assert second.manifest["generation"] == 2


def test_verifier_does_not_need_output_file(material):
    header, key = material
    entry, stream = records(header, key)[0]
    assert (
        crypto.verify_stream(
            stream,
            key,
            crypto.build_aad(header["vault_id"], crypto.FILE, entry["id"]),
            crypto.FILE,
        )
        == 14
    )
    stream.seek(0)
    data = bytearray(stream.read())
    data[-1] ^= 1
    with pytest.raises(crypto.IntegrityError):
        crypto.verify_stream(
            io.BytesIO(data),
            key,
            crypto.build_aad(header["vault_id"], crypto.FILE, entry["id"]),
            crypto.FILE,
        )


def test_independently_encoded_golden_fixture():
    import base64, json
    from pathlib import Path

    data = json.loads(
        (Path(__file__).parent / "fixtures" / "capsule-v1.json").read_text()
    )
    opened = c.Capsule(io.BytesIO(base64.b64decode(data["capsule_base64"])))
    key = opened.authenticate(data["password"])
    opened.verify(bytes(key))
    entry = opened.manifest["entries"][0]
    assert entry["name"] == "fixture.txt"
    assert crypto.decrypt_bytes(
        opened.record(entry).read(),
        bytes(key),
        crypto.build_aad(opened.header["vault_id"], crypto.FILE, entry["id"]),
        crypto.FILE,
    ) == base64.b64decode(data["plaintext_base64"])


@pytest.mark.parametrize(
    "field,value",
    [
        ("offset", 1),
        ("offset", True),
        ("length", 999999999),
        ("size", -1),
        ("id", "../file"),
        ("name", "../escape"),
        ("sha256", "x" * 64),
    ],
)
def test_authenticated_but_invalid_manifest_refused(material, field, value):
    opened = c.Capsule(snapshot(material))
    opened.unlock(material[1])
    manifest = opened.manifest
    manifest["entries"][0][field] = value
    encrypted = crypto.encrypt_bytes(
        c.encode(manifest),
        material[1],
        crypto.build_aad(opened.header["vault_id"], crypto.MANIFEST),
        crypto.MANIFEST,
    )
    body = (
        c.PREFIX.pack(c.MAGIC, len(opened.header_bytes), len(encrypted))
        + opened.header_bytes
        + encrypted
        + c.Slice(opened.source, opened.objects_offset, opened.objects_size).read()
    )
    rebuilt = body + c.FOOTER.pack(
        c.END, len(body) + c.FOOTER.size, hashlib.sha256(body).digest()
    )
    with pytest.raises(ValueError):
        c.Capsule(io.BytesIO(rebuilt)).unlock(material[1])
