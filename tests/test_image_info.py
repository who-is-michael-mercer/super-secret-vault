import io
import os
from pathlib import Path
import struct
import zlib
import pytest
from relayvault import cover, image_info
from relayvault.terminal import Terminal
from test_carrier import carrier, image_bytes


def chunk(kind, data):
    return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))


def test_public_fields_and_carrier_disclosure(carrier):
    path, _ = carrier
    info=image_info.inspect(path)
    assert (info.width,info.height,info.depth,info.channels)==(1,1,8,'RGB')
    assert info.size==path.stat().st_size and info.chunks>3
    output=io.StringIO()
    cover.render(Terminal(output,effects=False),path)
    text=output.getvalue()
    for forbidden in ('rvLt','cipher','encryption','objects','authentication','password','vault_id'):
        assert forbidden not in text
    assert 'valid (all chunk CRCs)' in text and 'inspection complete' in text


def test_profile_is_detected_without_decoding_untrusted_metadata(tmp_path):
    path=tmp_path/'a.png'
    raw=image_bytes()
    path.write_bytes(raw[:-12]+chunk(b'sRGB',b'\0')+raw[-12:])
    assert image_info.inspect(path).profile=='sRGB'
    path.write_bytes(raw[:-12]+chunk(b'iCCP',b'\x1b[31mattack\0\0junk')+raw[-12:])
    info=image_info.inspect(path)
    assert info.profile=='embedded ICC (not evaluated)'
    assert 'attack' not in repr(cover.snapshot(path))


@pytest.mark.parametrize('mutate',[
    lambda b:b[:20],lambda b:b+b'trailer',lambda b:b[:40]+bytes([b[40]^1])+b[41:],
    lambda b:b'not png',lambda b:b[:8]+chunk(b'IHDR',bytes(13))+b[33:],
    lambda b:b[:8]+struct.pack('>I',0x7fffffff)+b'IHDR'+b[16:],
    lambda b:b[:33]+b[:33][8:]+b[33:]])
def test_malformed_is_neutral(tmp_path, mutate):
    path=tmp_path/'image.png'; path.write_bytes(mutate(image_bytes()))
    with pytest.raises(ValueError): image_info.inspect(path)
    source, structure, status=cover.snapshot(path)
    assert status=='inspection incomplete' and structure==[('inspection','unavailable')]


def test_special_files_and_terminal_control_names(tmp_path):
    path=tmp_path/'bad\x1b[2J.png'; path.write_bytes(image_bytes())
    assert '\x1b' not in cover.display(path.name)
    fifo=tmp_path/'fifo'; os.mkfifo(fifo)
    assert cover.snapshot(fifo)[2]=='source unavailable'
    with pytest.raises(ValueError): image_info.inspect(fifo)


@pytest.mark.parametrize('width,height',[(8,5),(30,12),(80,24),(220,70)])
def test_cover_bounds_and_cached_scan(tmp_path,monkeypatch,width,height):
    path=tmp_path/'画像.png'; path.write_bytes(image_bytes())
    data=cover.snapshot(path)
    monkeypatch.setattr(cover.shutil,'get_terminal_size',lambda _:os.terminal_size((width,height)))
    monkeypatch.setattr(image_info,'inspect',lambda _:pytest.fail('unexpected rescan'))
    out=io.StringIO(); cover.render(Terminal(out,effects=False),path,data=data)
    assert len(out.getvalue().splitlines()) <= height-1
    for row in out.getvalue().splitlines():
        assert cover.clip(row,width-1)==row
    assert '>' not in out.getvalue() and '\x1b' not in out.getvalue()


def test_animated_png_is_explicitly_unsupported(tmp_path):
    raw=image_bytes(); path=tmp_path/'animated.png'
    path.write_bytes(raw[:33]+chunk(b'acTL',struct.pack('>II',2,0))+raw[33:])
    with pytest.raises(ValueError,match='Animated PNG'):
        image_info.inspect(path)
