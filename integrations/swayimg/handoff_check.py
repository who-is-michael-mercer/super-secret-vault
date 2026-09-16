"""Live native viewer/request socket check; no injected keys or terminal launch."""
import argparse
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
from relayvault import door, settings, image_info
from run_probe import fixture_module

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('binary',type=Path)
args=parser.parse_args()
with tempfile.TemporaryDirectory(prefix='relay-handoff-') as tmp:
    temp=Path(tmp)
    path=temp/'ordinary.png'; fixture_module.fixture(path)
    config=door.enroll(settings.defaults(),path)
    info=door.checked(config)
    (temp/'config.lua').write_text(door.lua_config(config))
    scripts=Path(door.__file__).parent/'swayimg'
    # Wrap initialization only in this test file; no seam ships in door.lua.
    (temp/'check.lua').write_text('''local register=swayimg.on_initialized
swayimg.on_initialized=function(f)
    register(function()
        f()
        swayimg.defer(.3,function()
            local i=swayimg.viewer.get_image()
            assert(i.relay_current and i.relay_original)
            assert(swayimg.relay_request(i.relay_origin))
            swayimg.exit()
        end)
    end)
end
'''+'dofile('+door.lua_string(str(scripts/'door.lua'))+')\n')
    parent,peer=socket.socketpair(socket.AF_UNIX,socket.SOCK_DGRAM)
    try:
        env=os.environ | {'RELAY_SWAYIMG_DOOR':'1','RELAY_SWAYIMG_REQUEST_FD':str(peer.fileno()),
            'RELAY_SWAYIMG_SCRIPTS':str(scripts),'RELAY_SWAYIMG_CONFIG':str(temp/'config.lua')}
        process=subprocess.Popen([str(args.binary.resolve()),'--config',str(temp/'check.lua'),str(path)],
            env=env,pass_fds=(peer.fileno(),),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        peer.close(); parent.settimeout(8)
        try:
            assert parent.recv(256).decode()==info.stamp
            out,err=process.communicate(timeout=8)
            assert process.returncode==0 and not err,(out,err)
        finally:
            if process.poll() is None:
                process.terminate(); process.wait(timeout=5)
    finally:
        parent.close(); peer.close()
print('PASS shipped Lua initializes in native Wayland; inherited datagram carries exact decoded stamp')
