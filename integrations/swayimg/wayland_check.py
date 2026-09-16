"""Actual Wayland viewer tests using fixed Lua view commands, never injected keys."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
from run_probe import ROOT, prepare, fixture_module


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('binary',type=Path)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    results={}
    with tempfile.TemporaryDirectory(prefix='relay-swayimg-wayland-') as tmp:
        directory=Path(tmp)/'session'
        env=prepare(directory)
        env['RELAY_SWAYIMG_TESTING']='1'
        wrapper=directory/'test.lua'
        wrapper.write_text('local probe=dofile('+json.dumps(str(ROOT/'probe.lua'))+')\n'+r'''
local dir = os.getenv('RELAY_SWAYIMG_PROBE')
local actions = {
    seed=probe.seed_partial,
    status_show=function() swayimg.text.status='render check' end,
    status_clear=function() swayimg.text.status='' end,
    zoom=function() swayimg.viewer.scale=1.5 end,
    reset=function() swayimg.viewer.reset() end,
    pan=function() swayimg.viewer.set_abs_position(-600, -400) end,
    next=function() swayimg.viewer.open('next') end,
    prev=function() swayimg.viewer.open('prev') end,
    reload=function() swayimg.viewer.reload() end,
    rotate=function() swayimg.viewer.rotate(90) end,
    mirror=function() swayimg.viewer.flip_horizontal() end,
    resize=function() swayimg.fullscreen=true end,
    restore=function() swayimg.fullscreen=false end,
}
swayimg.viewer.on_signal('USR1',function()
    local f=assert(io.open(dir..'/command','r'))
    local cmd=f:read('*a'); f:close()
    if cmd=='zoom' or cmd=='pan' or cmd=='rotate' or cmd=='mirror' or cmd=='resize' then
        probe.seed_partial()
    end
    assert(actions[cmd])()
end)
''')
        errors=(directory/'errors.txt').open('w')
        process=subprocess.Popen([str(args.binary.resolve()),'--config',str(wrapper),
            str(directory/'grid.png'),str(directory/'other/grid.png')],env=env,
            stdin=subprocess.DEVNULL,stdout=errors,stderr=errors)
        extra=None
        def wait(predicate,timeout=5):
            deadline=time.monotonic()+timeout
            latest=None
            while time.monotonic()<deadline:
                if process.poll() is not None:
                    raise AssertionError((directory/'errors.txt').read_text())
                try:
                    latest=json.loads((directory/'latest.json').read_text())
                    if predicate(latest): return latest
                except (FileNotFoundError,json.JSONDecodeError): pass
                time.sleep(.05)
            raise AssertionError(f'Condition timed out: {latest}')
        def command(name):
            (directory/'command').write_text(name)
            process.send_signal(signal.SIGUSR1)
        def record(label,state):
            assert state['matches']==0 and not state['eligible']
            assert state['prefix']==0, 'Partial prefix survived invalidation'
            assert not state['counts'], 'Unexpected physical input during automated run'
            results[label]=state
            print('PASS',label,flush=True)
        try:
            initial=wait(lambda s:s['visual'] and s['focused'])
            record('native_wayland_visual_and_focus',initial)
            command('status_show')
            shown=wait(lambda s:s['redraws']>initial['redraws'])
            command('status_clear')
            record('empty_status_redraw',wait(lambda s:s['redraws']>shown['redraws']))
            command('zoom')
            record('wrong_zoom',wait(lambda s:s['pose']['scale']==1.5 and not s['visual']))
            command('reset'); wait(lambda s:s['visual'])
            command('pan')
            record('wrong_viewport',wait(lambda s:not s['visual'] and s['pose']['x']<0))
            command('reset'); wait(lambda s:s['visual'])
            command('seed'); wait(lambda s:s['prefix']==2)
            command('next')
            record('same_basename_other_directory',wait(lambda s:s['pose']['path'].endswith('/other/grid.png')))
            command('prev'); restored=wait(lambda s:s['visual'])
            record('image_switch_history',restored)
            target=directory/'grid.png'
            command('seed'); wait(lambda s:s['prefix']==2)
            target.rename(directory/'renamed.png')
            record('rename_rejects_stale_display',wait(lambda s:not s['pose']['current']))
            (directory/'renamed.png').rename(target)
            command('reload'); reloaded=wait(lambda s:s['visual'])
            record('rename_reload',reloaded)
            old=target.stat()
            replacement=directory/'replacement.png'
            fixture_module.fixture(replacement,variant=2)
            os.utime(replacement,ns=(old.st_atime_ns,old.st_mtime_ns))
            command('seed'); wait(lambda s:s['prefix']==2)
            replacement.replace(target)
            stale=wait(lambda s:not s['pose']['current'])
            assert stale['pose']['generation']==reloaded['pose']['generation']
            record('atomic_replacement_preserved_mtime',stale)
            command('next'); wait(lambda s:s['pose']['path'].endswith('/other/grid.png'))
            command('prev')
            cached=wait(lambda s:s['pose']['path']==str(target))
            assert not cached['visual'] and not cached['pose']['current']
            record('stale_history_cache_rejected',cached)
            command('reload'); fresh=wait(lambda s:s['visual'])
            assert fresh['pose']['generation']!=reloaded['pose']['generation']
            record('replacement_explicit_reload',fresh)
            command('rotate')
            record('rotation_rejected',wait(lambda s:not s['pose']['original']))
            command('reload'); wait(lambda s:s['visual'])
            command('mirror')
            record('mirror_rejected',wait(lambda s:not s['pose']['original']))
            command('reload'); normal=wait(lambda s:s['visual'])
            command('resize')
            record('resize_redraw',wait(lambda s:s['visual'] and
                (s['pose']['window_width'],s['pose']['window_height']) !=
                (normal['pose']['window_width'],normal['pose']['window_height'])))
            # Fullscreen configure is asynchronous. A toggle/read of the old
            # property can request fullscreen again; wait for restored geometry.
            command('restore'); wait(lambda s:s['visual'] and
                (s['pose']['window_width'],s['pose']['window_height']) ==
                (normal['pose']['window_width'],normal['pose']['window_height']))
            command('seed'); wait(lambda s:s['prefix']==2)
            otherdir=Path(tmp)/'second'; otherenv=prepare(otherdir)
            extra=subprocess.Popen([str(args.binary.resolve()),'--config',str(ROOT/'probe.lua'),
                str(otherdir/'grid.png')],env=otherenv,stdin=subprocess.DEVNULL,
                stdout=errors,stderr=errors)
            record('focus_leave_other_viewer',wait(lambda s:not s['focused']))
            extra.terminate(); extra.wait(timeout=5); extra=None
            record('focus_return',wait(lambda s:s['focused']))
            assert not (directory/'errors.txt').read_text(), 'Viewer emitted diagnostics'
        finally:
            for child in (extra,process):
                if child is not None and child.poll() is None:
                    child.terminate(); child.wait(timeout=5)
            errors.close()
            args.report.parent.mkdir(parents=True,exist_ok=True)
            args.report.write_text(json.dumps(results,indent=2)+'\n')
    print(f'{len(results)} actual Wayland checks passed')


if __name__=='__main__': main()
