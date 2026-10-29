"""Tests for CLI play helpers."""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import os
import subprocess
import io
import json

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PLAY_PATH = ROOT / "python" / "play.py"

sys.path.insert(0, str(ROOT / "python"))
spec = importlib.util.spec_from_file_location("play_module_for_tests", PLAY_PATH)
play = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(play)


def test_quit_save_defaults_to_save_dir(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")

    path = play._quit_with_save(None, "Ironclad", "seed123")

    assert path is not None
    assert path.startswith(play.SAVE_DIR)
    assert path.endswith(".save")


@pytest.mark.parametrize("character", ["Ironclad", "Silent", "Defect", "Regent", "Necrobinder"])
def test_interactive_launcher_without_steam_fallback(character):
    """Exercise the actual user entry point, including its default DLL search path."""
    env = os.environ.copy()
    env.pop("STS2_GAME_DIR", None)
    result = subprocess.run(
        [sys.executable, str(PLAY_PATH), "--character", character,
         "--seed", "cli_5005", "--lang", "en", "--no-log"],
        input="quit\nn\n", capture_output=True, text=True,
        cwd=ROOT, env=env, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Neow" in result.stdout, result.stdout + result.stderr
    assert "TypeInitializationException" not in result.stdout


def test_setup_repairs_missing_module_dependency(monkeypatch):
    isfile = os.path.isfile
    dependency = os.path.join(play.LIB_DIR, "Sentry.Godot.dll")
    monkeypatch.setattr(os.path, "isfile", lambda path: False if path == dependency else isfile(path))
    monkeypatch.setattr(play, "_find_game_dir", lambda: "/test/steam/data")
    calls = []
    monkeypatch.setattr(play.subprocess, "run", lambda args, **kwargs: calls.append((args, kwargs)))
    monkeypatch.delenv("STS2_GAME_DIR", raising=False)
    play.ensure_setup()
    assert calls == [(["bash", os.path.join(play.ROOT, "setup.sh"), "/test/steam/data"],
                      {"cwd": play.ROOT, "check": True})]


def test_interactive_timeout_stops_without_proceeding_or_declaring_death(monkeypatch, capsys):
    responses = [
        {"type": "ready"},
        {"type": "decision", "decision": "combat_play", "round": 2,
         "player": {"hp": 57}, "hand": [], "energy": 0, "enemies": []},
        {"type": "error", "error_code": "combat_turn_timeout", "message": "Turn stalled",
         "player": {"hp": 52}},
        {"type": "quit_result"},
    ]
    sent = io.StringIO()

    class Process:
        stdin = sent
        stdout = io.StringIO("".join(json.dumps(r) + "\n" for r in responses))

        def terminate(self):
            pass

        def wait(self, **kwargs):
            pass

    monkeypatch.setattr(play.subprocess, "Popen", lambda *args, **kwargs: Process())
    monkeypatch.setattr(play, "LANG", "en")
    monkeypatch.setattr(play, "show_combat", lambda state: None)
    play.play(seed="timeout", auto=True, log=False)

    commands = [json.loads(line) for line in sent.getvalue().splitlines()]
    assert [cmd.get("action", cmd["cmd"]) for cmd in commands] == ["start_run", "end_turn", "quit"]
    output = capsys.readouterr().out
    assert "Stopping without recording a defeat" in output
