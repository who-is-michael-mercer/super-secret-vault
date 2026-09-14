"""Build pinned Swayimg in a new owner-local directory; never install system files."""
import argparse
import json
from pathlib import Path
import subprocess

root=Path(__file__).resolve().parent
pin=json.loads((root/'upstream.json').read_text())
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('destination',type=Path)
parser.add_argument("--probe", action="store_true", help="Build the historical Stage 1B patch")
args=parser.parse_args()
patch=root/("relay-probe.patch" if args.probe else "relay-door.patch")
destination=args.destination.absolute()
if destination.exists(): parser.error('destination must be new')
def run(*cmd): subprocess.run(cmd,check=True)
run('git','clone',pin['repository'],str(destination))
run('git','-C',str(destination),'checkout','--detach',pin['commit'])
run('git','-C',str(destination),'apply','--check',str(patch))
run('git','-C',str(destination),'apply',str(patch))
run('meson','setup',str(destination/'build'),str(destination),
    '-Dauto_features=disabled','-Dwayland=enabled','-Dpng=enabled',
    '-Dliblua=lua','-Dman=false','-Ddesktop=false')
run('meson','compile','-C',str(destination/'build'),'-j','3')
