"""Exercise the bridge entry point without starting an engine or HTTP listener."""
import io
import os
from pathlib import Path
import runpy
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("sdk", ["/portable/sdk/dotnet", None])
@pytest.mark.parametrize("game_dir", [None, "/custom/game/data"])
def test_bridge_launches_from_any_directory(monkeypatch, tmp_path, sdk, game_dir):
    calls = []

    class Process:
        stdin = io.StringIO()
        stdout = io.StringIO('{"type":"ready"}\n')
        stderr = io.StringIO()

    def popen(args, **kwargs):
        calls.append((args, kwargs, os.environ.get("STS2_GAME_DIR")))
        return Process()

    class Server:
        def __init__(self, address, handler):
            self.address = address

        def serve_forever(self):
            pass

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", [str(ROOT / "agent/sts2_bridge.py")])
    monkeypatch.setattr("subprocess.Popen", popen)
    monkeypatch.setattr("shutil.which", lambda name: sdk)
    monkeypatch.setattr("http.server.HTTPServer", Server)
    if game_dir is None:
        monkeypatch.delenv("STS2_GAME_DIR", raising=False)
    else:
        monkeypatch.setenv("STS2_GAME_DIR", game_dir)

    runpy.run_path(str(ROOT / "agent/sts2_bridge.py"), run_name="__main__")

    assert len(calls) == 1
    args, kwargs, environment = calls[0]
    assert args == [sdk or os.path.expanduser("~/.dotnet-arm64/dotnet"),
                    "run", "--no-build", "--project",
                    str(ROOT / "src/Sts2Headless/Sts2Headless.csproj")]
    assert Path(args[-1]).is_file()
    assert kwargs["cwd"] == str(ROOT)
    assert environment == (game_dir or str(ROOT / "lib"))
