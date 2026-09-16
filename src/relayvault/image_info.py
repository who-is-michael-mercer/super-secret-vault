"""Public PNG structure only; no capsule interpretation or decryption."""

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat
import struct
import zlib

SIGNATURE = b'\x89PNG\r\n\x1a\n'
MAX_FILE = 1152 * 1024 * 1024
MAX_IMAGE = 128 * 1024 * 1024


def stamp(info):
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
        raise ValueError('Image must be an owner-controlled regular file without aliases.')
    return ':'.join(str(v) for v in (info.st_dev, info.st_ino, info.st_size,
        info.st_mtime_ns // 10**9, info.st_mtime_ns % 10**9,
        info.st_ctime_ns // 10**9, info.st_ctime_ns % 10**9))


def current(path, expected):
    try:
        p = Path(path)
        return str(p.resolve(strict=True)) == str(p) and stamp(p.lstat()) == expected
    except (OSError, ValueError, RuntimeError):
        return False


@dataclass(frozen=True)
class ImageInfo:
    path: str
    stamp: str
    binding: str
    width: int
    height: int
    depth: int
    channels: str
    profile: str
    size: int
    chunks: int


def inspect(path):
    path = str(Path(path).expanduser().absolute())
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        identity = stamp(before)
        if not current(path, identity) or not 45 <= before.st_size <= MAX_FILE:
            raise ValueError('Image identity or size is unavailable.')
        def exact(n):
            data = stream.read(n)
            if len(data) != n:
                raise ValueError('Incomplete PNG structure.')
            return data
        if exact(8) != SIGNATURE:
            raise ValueError('Not a PNG image.')
        digest = hashlib.sha256(SIGNATURE)
        ordinary = 8
        chunks = 0
        width = height = depth = color = 0
        profile = 'unspecified'
        idat = False
        palette = False
        while True:
            header = exact(8)
            length, kind = struct.unpack('>I4s', header)
            chunks += 1
            if chunks > 100000 or length > 0x7fffffff or stream.tell()+length+4 > before.st_size or not all(65 <= b <= 90 or 97 <= b <= 122 for b in kind) or not 65 <= kind[2] <= 90:
                raise ValueError('Invalid PNG structure.')
            if chunks == 1 and (kind != b'IHDR' or length != 13):
                raise ValueError('Invalid PNG header.')
            if kind == b'acTL':
                raise ValueError('Animated PNG inspection is unsupported.')
            if kind == b'IHDR' and chunks != 1:
                raise ValueError('Duplicate PNG header.')
            public = kind != b'rvLt'
            if public:
                ordinary += length + 12
                if ordinary > MAX_IMAGE:
                    raise ValueError('PNG image data exceeds inspection limit.')
                digest.update(header)
            crc = zlib.crc32(kind)
            remaining = length
            prefix = b''
            while remaining:
                data = exact(min(65536, remaining))
                if len(prefix) < 80:
                    prefix += data[:80-len(prefix)]
                crc = zlib.crc32(data, crc)
                if public:
                    digest.update(data)
                remaining -= len(data)
            trailer = exact(4)
            if struct.unpack('>I', trailer)[0] != crc:
                raise ValueError('PNG checksum did not verify.')
            if public:
                digest.update(trailer)
            if kind == b'IHDR':
                width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', prefix)
                depths = {0:(1,2,4,8,16), 2:(8,16), 3:(1,2,4,8), 4:(8,16), 6:(8,16)}
                if not width or not height or max(width,height) > 0x7fffffff or depth not in depths.get(color,()) or compression or filtering or interlace not in (0,1):
                    raise ValueError('Unsupported PNG header.')
            elif kind == b'PLTE':
                if idat or not length or length % 3 or length > 768:
                    raise ValueError('Invalid PNG palette.')
                palette = True
            elif kind == b'IDAT':
                if color == 3 and not palette:
                    raise ValueError('PNG palette missing.')
                idat = True
            elif kind == b'sRGB' and length == 1 and prefix[0] <= 3:
                profile = 'sRGB'
            elif kind == b'iCCP' and profile != 'sRGB':
                # Do not decompress or display untrusted ICC names/content.
                profile = 'embedded ICC (not evaluated)'
            elif kind == b'IEND':
                if length or not idat or stream.tell() != before.st_size:
                    raise ValueError('Invalid PNG ending.')
                break
        if stamp(os.fstat(stream.fileno())) != identity or not current(path, identity):
            raise ValueError('Image changed during inspection.')
    return ImageInfo(path, identity, digest.hexdigest(), width, height, depth,
        {0:'gray', 2:'RGB', 3:'indexed', 4:'gray + alpha', 6:'RGBA'}[color],
        profile, before.st_size, chunks)
