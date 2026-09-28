import os
import subprocess
import sys
import time

from yttoolkit import lifecycle, runstate
from yttoolkit.config import Paths
from yttoolkit.platform import current


def test_serve_then_stop(tmp_path):
    port = runstate.pick_port(range(8850, 8870))
    env = {**os.environ, "YT_TOOLKIT_DATA_ROOT": str(tmp_path), "YT_TOOLKIT_FFMPEG_PATH_LOOKUP": "0"}
    proc = subprocess.Popen([sys.executable, "-m", "yttoolkit", "serve", "--port", str(port)], env=env)
    paths = Paths(data_root=tmp_path)
    plat = current()
    try:
        deadline = time.monotonic() + 30
        info = None
        while time.monotonic() < deadline and info is None:
            info = lifecycle.find_running(paths, plat)
            time.sleep(0.2)
        assert info is not None, "serve ไม่ขึ้นภายใน 30 วินาที"
        assert info.port == port
        assert info.pid == proc.pid
        assert lifecycle.stop(paths, plat, out=lambda m: None) == 0
        assert proc.wait(timeout=15) == 0
        assert not paths.app_json.exists()
    finally:
        if proc.poll() is None:
            proc.kill()
