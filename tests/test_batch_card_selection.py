"""Batch clients must satisfy the engine's selection contract."""
import importlib.util
import io
import json
from pathlib import Path


def test_batch_respects_required_count_and_exported_indices(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root / "python"))
    spec = importlib.util.spec_from_file_location("batch_selection", root / "python/play_full_run.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    responses = [
        {"type": "ready"},
        {"type": "decision", "decision": "card_select", "min_select": 2,
         "max_select": 2, "cards": [{"index": 3}, {"index": 5}, {"index": 7}]},
        {"type": "decision", "decision": "game_over", "victory": False,
         "player": {"hp": 0}, "floor": 1, "act": 1},
    ]
    sent = io.StringIO()

    class Process:
        stdin = sent
        stdout = io.StringIO("".join(json.dumps(r) + "\n" for r in responses))

        def terminate(self):
            pass

        def wait(self, **kwargs):
            pass

    monkeypatch.setattr(runner.subprocess, "Popen", lambda *args, **kwargs: Process())
    runner.play_run("selection", verbose=False, log=False)
    commands = [json.loads(line) for line in sent.getvalue().splitlines()]
    assert commands[1] == {"cmd": "action", "action": "select_cards", "args": {"indices": "3,5"}}
