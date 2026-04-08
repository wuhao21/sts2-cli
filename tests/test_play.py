"""Tests for CLI play helpers."""

from __future__ import annotations

import importlib.util
import pathlib
import sys


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


def test_print_console_result_uses_to_string_fallback(capsys):
    play._print_console_result({"console": {"to_string": "ok"}})

    out = capsys.readouterr().out
    assert "[DevConsole]" in out
    assert "ok" in out


def test_print_console_result_renders_captured_output(capsys):
    play._print_console_result({"console": {"to_string": "ok"}, "output": "line one\nline two"})

    out = capsys.readouterr().out
    assert "[DevConsole]" in out
    assert "line one" in out
    assert "line two" in out


def test_should_record_replay_includes_console_commands():
    assert play._should_record_replay({"cmd": "action"}) is True
    assert play._should_record_replay({"cmd": "console"}) is True
    assert play._should_record_replay({"cmd": "get_map"}) is False
    assert play._should_record_replay({"cmd": "console"}, record=False) is False


def test_get_input_console_command_sends_bridge_request_and_refreshes_state(monkeypatch, capsys):
    sent = []
    original_state = {"decision": "event_choice", "player": {"gold": 99}}
    refreshed_state = {"decision": "event_choice", "player": {"gold": 222}}

    def fake_send(payload, record=True):
        sent.append((payload, record))
        return {
            "type": "console_result",
            "console": {"to_string": "ok"},
            "state": refreshed_state,
        }

    monkeypatch.setattr("builtins.input", lambda prompt="": "console gold 123")
    monkeypatch.setattr(play.get_input, "_send", fake_send, raising=False)

    result = play.get_input("Choose option", state=original_state)

    assert result == "__refresh__"
    assert sent == [({"cmd": "console", "input": "gold 123"}, True)]
    assert original_state == refreshed_state

    out = capsys.readouterr().out
    assert "[DevConsole]" in out
    assert "ok" in out
