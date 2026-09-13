"""Static PNG private-chunk transport; no pixel decoding or recompression."""

import bisect
import io
import os
import struct
import uuid
import zlib
from . import capsule as c

SIGNATURE = b"\x89PNG\r\n\x1a\n"
TYPE = b"rvLt"
SEGMENT = struct.Struct(">4sB16sII")
SEGMENT_SIZE = 1024 * 1024
MAX_IMAGE = 128 * 1024 * 1024
MAX_CHUNKS = 100000


def scan(source, *, recovery=False):
    size = source.seek(0, os.SEEK_END)
    if not 20 <= size <= c.MAX_CAPSULE + MAX_IMAGE:
        raise c.FormatError("Unsupported PNG size.")
    source.seek(0)
    if c.exact(source, 8) != SIGNATURE:
        raise c.FormatError("Not a PNG.")
    chunks = []
    segments = {}
    transport = None
    count = None
    seen_idat = False
    idat_closed = False
    seen_header = False
    seen_palette = False
    image_bytes = 0
    while source.tell() < size:
        start = source.tell()
        length, kind = struct.unpack(">I4s", c.exact(source, 8))
        if (
            length > 2**31 - 1
            or start + 12 + length > size
            or len(chunks) >= MAX_CHUNKS
        ):
            raise c.FormatError("Invalid PNG chunk bounds.")
        if (
            not all(65 <= x <= 90 or 97 <= x <= 122 for x in kind)
            or not 65 <= kind[2] <= 90
        ):
            raise c.FormatError("Invalid PNG chunk type.")
        if not recovery:
            if not chunks and (kind != b"IHDR" or length != 13):
                raise c.FormatError("Missing PNG header.")
            if kind in {b"acTL", b"fcTL", b"fdAT"}:
                raise c.FormatError("Animated PNG is not supported.")
            if kind[0] < 97 and kind not in {b"IHDR", b"PLTE", b"IDAT", b"IEND"}:
                raise c.FormatError("Unknown critical PNG chunk.")
            if kind == b"IHDR":
                if seen_header or length != 13:
                    raise c.FormatError("Duplicate PNG header.")
                seen_header = True
            if kind == b"PLTE":
                if (
                    seen_palette
                    or seen_idat
                    or length == 0
                    or length % 3
                    or length > 768
                ):
                    raise c.FormatError("Invalid palette.")
                seen_palette = True
            if kind == b"IDAT":
                if idat_closed:
                    raise c.FormatError("Nonconsecutive image data.")
                seen_idat = True
            elif seen_idat:
                idat_closed = True
            if kind == TYPE and not seen_idat:
                raise c.FormatError("Carrier chunks precede image data.")
        crc = zlib.crc32(kind)
        remaining = length
        first = b""
        while remaining:
            data = c.exact(source, min(remaining, SEGMENT_SIZE))
            if not first:
                first = data[: max(SEGMENT.size, 13)]
            crc = zlib.crc32(data, crc)
            remaining -= len(data)
        expected = struct.unpack(">I", c.exact(source, 4))[0]
        if crc != expected and (not recovery or kind == TYPE):
            raise c.FormatError("PNG chunk checksum failed.")
        if kind == b"IHDR" and not recovery:
            width, height, depth, color, compression, filtering, interlace = (
                struct.unpack(">IIBBBBB", first[:13])
            )
            depths = {
                0: {1, 2, 4, 8, 16},
                2: {8, 16},
                3: {1, 2, 4, 8},
                4: {8, 16},
                6: {8, 16},
            }
            if (
                not width
                or not height
                or depth not in depths.get(color, set())
                or compression
                or filtering
                or interlace not in {0, 1}
            ):
                raise c.FormatError("Invalid PNG image header.")
        if kind == TYPE:
            if not SEGMENT.size < length <= SEGMENT.size + SEGMENT_SIZE:
                raise c.FormatError("Invalid carrier segment size.")
            magic, version, identity, index, total = SEGMENT.unpack(
                first[: SEGMENT.size]
            )
            if (
                magic != b"RLYP"
                or version != 1
                or not 1 <= total <= 1024
                or index >= total
                or index in segments
            ):
                raise c.FormatError("Invalid or duplicate carrier segment.")
            if transport is not None and (transport != identity or count != total):
                raise c.FormatError("Mixed carrier segments.")
            transport, count = identity, total
            payload = length - SEGMENT.size
            if index < total - 1 and payload != SEGMENT_SIZE:
                raise c.FormatError("Short nonfinal carrier segment.")
            segments[index] = (start + 8 + SEGMENT.size, payload)
        else:
            image_bytes += length + 12
            if image_bytes > MAX_IMAGE:
                raise c.FormatError("PNG cover exceeds 128 MiB.")
        chunks.append((start, length + 12, kind))
        if kind == b"IEND":
            if length or source.tell() != size or not recovery and not seen_idat:
                raise c.FormatError("Invalid PNG ending.")
            break
    if not chunks or chunks[-1][2] != b"IEND":
        raise c.FormatError("Truncated PNG.")
    if segments and len(segments) != count:
        raise c.FormatError("Missing carrier segments.")
    return chunks, [segments[i] for i in range(count or 0)]


class Segments(io.RawIOBase):
    def __init__(self, source, spans):
        self.source = source
        self.spans = spans
        self.starts = []
        self.size = 0
        self.position = 0
        for _, length in spans:
            self.starts.append(self.size)
            self.size += length
        if self.size > c.MAX_CAPSULE:
            raise c.FormatError("Carrier payload exceeds limit.")

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=os.SEEK_SET):
        position = offset + (
            0
            if whence == 0
            else (
                self.position
                if whence == 1
                else self.size if whence == 2 else -(10**30)
            )
        )
        if not 0 <= position <= self.size:
            raise c.FormatError("Seek outside carrier.")
        self.position = position
        return position

    def read(self, size=-1):
        remaining = (
            self.size - self.position
            if size is None or size < 0
            else min(size, self.size - self.position)
        )
        result = []
        while remaining:
            index = bisect.bisect_right(self.starts, self.position) - 1
            offset, length = self.spans[index]
            inside = self.position - self.starts[index]
            amount = min(remaining, length - inside)
            self.source.seek(offset + inside)
            data = c.exact(self.source, amount)
            result.append(data)
            self.position += amount
            remaining -= amount
        return b"".join(result)


def capsule_stream(source, *, recovery=False):
    _, spans = scan(source, recovery=recovery)
    if not spans:
        raise c.FormatError("No Relay capsule in this image.")
    return Segments(source, spans)


def write_chunk(output, kind, data):
    c.crypto._write_all(
        output,
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data)),
    )


def embed(image, capsule, output, *, replace=False):
    chunks, segments = scan(image)
    if segments and not replace:
        raise c.FormatError("Source image already contains a carrier.")
    length = capsule.seek(0, os.SEEK_END)
    if not 0 < length <= c.MAX_CAPSULE:
        raise c.FormatError("Invalid capsule size.")
    total = (length + SEGMENT_SIZE - 1) // SEGMENT_SIZE
    transport = uuid.uuid4().bytes
    output.seek(0)
    output.truncate()
    c.crypto._write_all(output, SIGNATURE)
    for offset, size, kind in chunks:
        if kind == TYPE:
            continue
        if kind == b"IEND":
            capsule.seek(0)
            for index in range(total):
                data = capsule.read(SEGMENT_SIZE)
                write_chunk(
                    output,
                    TYPE,
                    SEGMENT.pack(b"RLYP", 1, transport, index, total) + data,
                )
        c.copy(c.Slice(image, offset, size), output)
    output.flush()
