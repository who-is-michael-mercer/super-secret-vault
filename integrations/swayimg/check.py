"""Build/run headless checks against the exact patched upstream objects."""
from pathlib import Path
import argparse
import shlex
import subprocess
import tempfile
import os
import struct
import zlib
from run_probe import ROOT, prepare

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('checkout', type=Path)
args = parser.parse_args()
checkout = args.checkout.resolve()
subprocess.run(['lua', str(ROOT/'test_matcher.lua')], cwd=ROOT.parent.parent, check=True)
subprocess.run(['lua', str(ROOT/'test_matcher.lua'), 'src/relayvault/swayimg/matcher.lua'], cwd=ROOT.parent.parent, check=True)
with tempfile.TemporaryDirectory(prefix='relay-swayimg-check-') as tmp:
    directory=Path(tmp)
    prepare(directory/'files')
    objects=sorted((checkout/'build/swayimg.p').glob('*.o'))
    objects=[str(p) for p in objects if p.name!='src_main.cpp.o']
    flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs',
        'wayland-client','xkbcommon','fontconfig','freetype2','lua','libpng'],text=True))
    binary=directory/'origin-test'
    subprocess.run(['c++','-std=c++20','-UNDEBUG','-pthread','-I'+str(checkout/'src'),
        '-I'+str(checkout/'build'),str(ROOT/'test_origin.cpp'),*objects,*flags,
        '-o',str(binary)],check=True)
    subprocess.run([str(binary),str(directory/'files')],check=True)
    prepare(directory/'production')
    raw=(directory/'production/grid.png').read_bytes()
    payload=bytes(17*1024*1024)
    chunk=struct.pack('>I',len(payload))+b'rvLt'+payload+struct.pack('>I',zlib.crc32(b'rvLt'+payload))
    (directory/'production/large.png').write_bytes(raw[:-12]+chunk+raw[-12:])
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
    for name,width,height in [('wide',16385,1),('pixels',8193,8192)]:
        compressor=zlib.compressobj()
        row=bytes(1+width*3)
        data=b''.join(compressor.compress(row) for _ in range(height))+compressor.flush()
        (directory/'production'/f'{name}.png').write_bytes(b'\x89PNG\r\n\x1a\n'+
            chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+
            chunk(b'IDAT',data)+chunk(b'IEND',b''))
    subprocess.run([str(binary),str(directory/'production')],check=True,
        env=os.environ | {'RELAY_SWAYIMG_DOOR':'1'})
