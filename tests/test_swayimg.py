import os
from pathlib import Path
import shutil
import subprocess
import pytest

ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.skipif(not shutil.which('lua'),reason='Lua is required by the optional viewer integration')
def test_shipped_lua_predicate(tmp_path):
    config=tmp_path/'config.lua'
    config.write_text("return {image='/image.png',x=350,y=250,width=100,height=100,zoom_min=.9,zoom_max=1.1,tolerance_x=.12,tolerance_y=.12,timeout=5,sequence={102,65,107,99,104,58,1,102}}")
    root=ROOT/'src/relayvault/swayimg'
    subprocess.run(['lua',str(ROOT/'integrations/swayimg/test_door.lua'),str(root/'door.lua')],check=True,
        env=os.environ | {'RELAY_SWAYIMG_SCRIPTS':str(root),'RELAY_SWAYIMG_CONFIG':str(config)})

@pytest.mark.skipif(not shutil.which('lua'),reason='Lua is required by the optional viewer integration')
def test_shipped_matcher():
    subprocess.run(['lua',str(ROOT/'integrations/swayimg/test_matcher.lua'),
        str(ROOT/'src/relayvault/swayimg/matcher.lua')],check=True,cwd=ROOT)
