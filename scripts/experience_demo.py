"""Create/run a disposable Relay experience. Public demo password: 13001300."""
import argparse
import math
import os
from pathlib import Path
import random
import struct
import sys
import zlib

REPO=Path(__file__).resolve().parents[1]


def image(path):
    """A small original night landscape; ordinary PNG with no visible Relay marks."""
    width,height=800,600
    pixels=bytearray(width*height*3)
    for y in range(height):
        t=y/height
        for x in range(width):
            color=(int(12+35*t),int(22+36*t),int(39+37*t))
            if y>405+45*math.sin(x/115)+25*math.sin(x/43): color=(23,39,48)
            if y>485+30*math.sin(x/140+.5): color=(14,29,36)
            if (x-400)**2+(y-285)**2<38**2: color=(213,215,195)
            offset=(y*width+x)*3
            pixels[offset:offset+3]=bytes(color)
    rng=random.Random(13)
    for _ in range(110):
        x,y=rng.randrange(width),rng.randrange(360)
        if (x-400)**2+(y-285)**2>55**2:
            offset=(y*width+x)*3
            pixels[offset:offset+3]=bytes((126,145,154))
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
    raw=b''.join(b'\0'+pixels[y*width*3:(y+1)*width*3] for y in range(height))
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+
        chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+
        chunk(b'sRGB',b'\0')+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b''))


def prepare(directory):
    from relayvault import door, settings
    from relayvault.vault import capsule, store
    from relayvault.vault.session import VaultSession
    target=directory/'evening.png'
    if target.exists():
        if not (directory/'state/preferences.json').is_file():
            raise ValueError('Existing demo has no local policy; use a new --directory.')
        return target
    directory.mkdir(mode=0o700,parents=True,exist_ok=False)
    source=directory/'original.png'; image(source)
    header,key=capsule.metadata('13001300')
    try:
        store.create(target,header,bytes(key),image=source)
    finally:
        key[:]=bytes(len(key))
    note=directory/'welcome.txt'
    note.write_text('Disposable Relay demonstration.\nThis carrier uses the public password 13001300.\nUse your own carrier and password for private material.\n')
    with VaultSession.authenticate('13001300',target) as session:
        session.store(note)
    settings.save(door.enroll(settings.defaults(),target))
    return target


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,default=REPO/'.local/demo')
    group=parser.add_mutually_exclusive_group()
    group.add_argument('--prepare-only',action='store_true')
    group.add_argument('--terminal',action='store_true',help='Start directly at the image inspector')
    group.add_argument('--maintenance',action='store_true',help='Start directly at real password authentication')
    args=parser.parse_args()
    directory=args.directory.expanduser().absolute()
    os.environ['RELAY_HOME']=str(directory/'state')
    target=prepare(directory)
    print('Disposable carrier:',target)
    print('Public demo password: 13001300')
    print('No real private data belongs in this demo.',flush=True)
    if args.prepare_only: return
    argv=[sys.executable,'-m','relayvault']
    if args.terminal or args.maintenance:
        argv += ['maintenance' if args.maintenance else 'open',str(target)]
    else:
        viewer=REPO/'.local/swayimg/build/swayimg'
        if not viewer.is_file():
            parser.error('Build the pinned viewer first; see integrations/swayimg/README.md')
        argv += ['view','--viewer',str(viewer)]
    os.execv(sys.executable,argv)


if __name__=='__main__': main()
