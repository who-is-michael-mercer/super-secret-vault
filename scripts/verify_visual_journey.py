"""Live native Swayimg/Foot qualification with explicit viewer-local test events.

No desktop key injection or capture. A test-only Lua wrapper feeds the shipped
matcher; a nested PTY driver types known input into the real Relay child in Foot.
This validates integration, not a new physical-key qualification.
"""
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import time

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'tests'))
from test_cli import Process
import conftest


class DisplayProcess(Process):
    def wait_for(self,needle,timeout=10):
        needle=needle.encode() if isinstance(needle,str) else needle
        start=len(self.data); deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if select.select([self.master],[],[],.05)[0]:
                try: chunk=os.read(self.master,65536)
                except OSError: break
                self.data+=chunk
                sys.stdout.buffer.write(chunk); sys.stdout.buffer.flush()
                if needle in self.data[start:]: return self.data[start:]
            if self.process.poll() is not None: break
        raise AssertionError(f'Missing {needle!r}, exit={self.process.poll()}')


def ritual(app):
    app.wait_for('inspection complete')
    app.send(b'\x1b[H\x1b[19~\x1b[5~\x1b[F')
    app.wait_for('R / 13'); time.sleep(.15)
    app.send(b'\x1b[D\x1b[C\x1b[18~\x1b[H')
    app.wait_for('route table retained')
    app.send('peel\r'); app.wait_for('layer 3')
    app.send('follow 3\r'); app.wait_for('roundtrip: below useful precision')
    app.send('open\r'); app.wait_for('password: ')
    app.send('13001300\r'); app.wait_for('session: active')


def terminal_driver(job, command):
    phase=2 if (job/'done1.json').exists() else 1
    try:
        assert command[1:3]==['-m','relayvault'] and command[3]=='_door-open'
        with DisplayProcess(command[3:],job/'state',python=command[0]) as app:
            ritual(app)
            if phase==1:
                source=job/'roundtrip.txt'; source.write_text('Live native journey.\n')
                app.send(f'store "{source}" roundtrip\r'); app.wait_for('store: verified and committed')
                app.send(f'retrieve roundtrip "{job / "retrieved.txt"}"\r')
                app.wait_for('retrieve: authenticated and written')
                assert (job/'retrieved.txt').read_bytes()==source.read_bytes()
                app.send('lock\r'); ritual(app)
            app.send('list\r'); app.wait_for('roundtrip —')
            app.send('exit\r'); app.wait_for(b'\x1b[?1049l'); app.finish()
            assert b'13001300' not in app.data
        (job/f'done{phase}.json').write_text(json.dumps({'phase':phase,'termios_restored':True,'result':'passed'}))
    except BaseException as error:
        (job/'failure.txt').write_text(repr(error))
        raise


def main():
    from relayvault import door, settings
    from experience_demo import prepare
    started=time.monotonic()
    binary=(REPO/'.local/swayimg/build/swayimg').resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix='relay-live-') as temp:
        job=Path(temp)/'case'
        os.environ['RELAY_HOME']=str(job/'state')
        target=prepare(job)
        config=settings.load() | {'animation_speed':'fast'}
        settings.save(config)
        initial=door.checked(config)
        original_module=door.__file__
        original_scripts=Path(door.__file__).parent/'swayimg'
        scripts=job/'swayimg'; scripts.mkdir()
        (scripts/'matcher.lua').write_bytes((original_scripts/'matcher.lua').read_bytes())
        wrapper=r'''
local job=__JOB__
local event, focused, requests, phase = nil,false,0,0
local down, drawn = {}, nil
local M=dofile(os.getenv('RELAY_SWAYIMG_SCRIPTS')..'/matcher.lua')
local c=dofile(os.getenv('RELAY_SWAYIMG_CONFIG'))
local function pose()
    local i=swayimg.viewer.get_image()
    if not i then return nil end
    local p,w=swayimg.viewer.get_position(),swayimg.get_window_size()
    return {path=i.path,origin_path=i.relay_path,current=i.relay_current,
        original=i.relay_original,origin=i.relay_origin,generation=i.relay_generation,
        width=i.width,height=i.height,x=p.x,y=p.y,scale=swayimg.viewer.scale,
        window_width=w.width,window_height=w.height}
end
local function signature(p)
    if not p then return '' end
    local values={}
    for k,v in pairs(p) do values[#values+1]=k..'='..tostring(v) end
    table.sort(values); return table.concat(values, ';')
end
local function eligible()
    local p=pose()
    return focused and next(down)==nil and drawn==signature(p) and M.geometry(p,c)
end
local register_draw=swayimg.on_redrawn
swayimg.on_redrawn=function(f)
    register_draw(function() f(); drawn=signature(pose()) end)
end
local register_event=swayimg.on_relay_event
swayimg.on_relay_event=function(f)
    event=f
    register_event(function(kind,code)
        if kind=='enter' then focused=true; down={}
        elseif kind=='leave' then focused=false; down={}
        elseif kind=='held' or kind=='press' then down[code]=true
        elseif kind=='release' then down[code]=nil end
        f(kind,code)
    end)
end
local request=swayimg.relay_request
swayimg.relay_request=function(stamp)
    local ok=request(stamp)
    if ok then requests=requests+1 end
    local f=assert(io.open(job..'/requests','w')); f:write(requests); f:close()
    return ok
end
local register_init=swayimg.on_initialized
swayimg.on_initialized=function(f)
    register_init(function()
        f()
        -- Keep the test's own view under the pointer; no compositor polling or
        -- synthetic focus events. Production remains an ordinary window.
        swayimg.fullscreen=true
        local start=swayimg.relay_time()
        local function exists(name)
            local f=io.open(job..'/'..name,'r')
            if f then f:close(); return true end
            return false
        end
        local function feed()
            -- Explicit local synthetic unit events, never desktop/physical input.
            for _,code in ipairs({102,65,107,99,104,58,1,102}) do
                event('press',code); event('release',code)
            end
        end
        local function tick()
            if exists('failure.txt') or exists('done2.json') then swayimg.exit(); return end
            if swayimg.relay_time()-start>40 then
                local f=assert(io.open(job..'/failure.txt','w'))
                f:write('live journey timeout; phase=',phase,'; requests=',requests,
                    '; focused=',tostring(focused),'; held=',tostring(next(down)~=nil),
                    '; pose=',signature(pose()),'; drawn=',tostring(drawn)); f:close()
                swayimg.exit(); return
            end
            local i=swayimg.viewer.get_image()
            if phase==0 and eligible() then
                feed(); phase=1
            elseif phase==1 and exists('done1.json') and focused then
                assert(not i.relay_current,'Old displayed image incorrectly remained current')
                local f=assert(io.open(job..'/stale-rejected','w')); f:write('true'); f:close()
                swayimg.viewer.reload(); phase=2
            elseif phase==2 and eligible() then
                feed(); phase=3
            end
            swayimg.defer(.25,tick)
        end
        swayimg.defer(.5,tick)
    end)
end
dofile(__SHIPPED__)
-- Set the load policy before decoding, not scale on an image still loading.
swayimg.viewer.default_scale=1
'''.replace('__JOB__',door.lua_string(str(job))).replace('__SHIPPED__',door.lua_string(str(original_scripts/'door.lua')))
        (scripts/'door.lua').write_text(wrapper)
        actual_argv=door.terminal_argv
        calls=[]
        def wrapped(info,foot):
            argv=actual_argv(info,foot)
            calls.append(argv)
            return argv[:3]+[sys.executable,str(Path(__file__).resolve()),'--terminal-driver',str(job),*argv[3:]]
        door.__file__=str(job/'door.py')  # Select only the explicit test Lua wrapper.
        door.terminal_argv=wrapped
        try:
            result=door.view(config,str(binary))
        finally:
            door.__file__=original_module
            door.terminal_argv=actual_argv
        assert not (job/'failure.txt').exists(), (job/'failure.txt').read_text() if (job/'failure.txt').exists() else ''
        assert result==0 and len(calls)==2
        assert (job/'requests').read_text()=='2' and (job/'stale-rejected').read_text()=='true'
        assert all(json.loads((job/f'done{n}.json').read_text())['termios_restored'] for n in (1,2))
        final=door.checked(config)
        assert final.binding==initial.binding and final.stamp!=initial.stamp
        fd=door.acquire_lock(str(target)); os.close(fd)
        assert not list((job/'state').glob('.viewer-*'))
        report={'result':'passed','terminal_launches':len(calls),'viewer_local_synthetic_sequences':2,
            'real_physical_sequences':0,'password_sessions':3,'store_retrieve':True,
            'stale_rejected_and_reloaded':True,'duplicate_lock_released':True,
            'terminal_settings_restored':True,'temporary_viewer_config_removed':True,
            'seconds':round(time.monotonic()-started,2)}
        (REPO/'.local/live-verification.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--terminal-driver':
        terminal_driver(Path(sys.argv[2]),sys.argv[3:])
    else:
        main()
