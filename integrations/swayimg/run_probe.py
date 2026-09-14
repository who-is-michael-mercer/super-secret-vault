"""Open one disposable Stage 1B viewer; never launch Relay or inject keys."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('imv_fixture', ROOT.parent / 'imv/run_probe.py')
fixture_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture_module)


def prepare(directory):
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    (directory / 'other').mkdir()
    fixture_module.fixture(directory / 'grid.png')
    fixture_module.fixture(directory / 'other/grid.png', variant=1)
    config = {'image': str(directory / 'grid.png'), 'x': 350, 'y': 250,
              'width': 100, 'height': 100, 'zoom_min': .9, 'zoom_max': 1.1,
              'tolerance_x': .12, 'tolerance_y': .12}
    (directory / 'config.lua').write_text('return {' + ','.join(
        f'{k}={json.dumps(v)}' for k, v in config.items()) + '}\n')
    return os.environ | {'RELAY_SWAYIMG_PROBE': str(directory),
                         'RELAY_SWAYIMG_SCRIPTS': str(ROOT)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('binary', type=Path)
    parser.add_argument('--directory', type=Path)
    args = parser.parse_args()
    directory = args.directory or Path(tempfile.mkdtemp(prefix='relay-swayimg-')) / 'session'
    directory = directory.absolute()
    env = prepare(directory)
    with (directory / 'viewer-errors.txt').open('w') as errors:
        process = subprocess.Popen([str(args.binary.resolve()), '--config', str(ROOT/'probe.lua'),
            '--size', '900,700', str(directory/'grid.png'), str(directory/'other/grid.png')],
            env=env, stdin=subprocess.DEVNULL, stdout=errors, stderr=errors)
        print(json.dumps({'pid': process.pid, 'directory': str(directory)}), flush=True)
        try:
            return process.wait()
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)


if __name__ == '__main__':
    raise SystemExit(main())
