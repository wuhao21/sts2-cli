"""Exercise a real engine phase stall without exposing fault injection in the API."""
import json
from pathlib import Path
import subprocess

import pytest

from conftest import DOTNET

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tests" / "EngineProbe" / "EngineProbe.csproj"


@pytest.fixture(scope="module")
def engine_probe():
    built = subprocess.run(
        [DOTNET, "build", str(PROBE), "--ignore-failed-sources", "-p:NuGetAudit=false"],
        capture_output=True, text=True, timeout=120,
    )
    assert built.returncode == 0, built.stdout + built.stderr

    def run(scenario):
        result = subprocess.run(
            [DOTNET, str(PROBE.parent / "bin/Debug/net9.0/EngineProbe.dll"), str(ROOT), scenario],
            capture_output=True, text=True, cwd=ROOT, timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        return json.loads(next(line for line in reversed(result.stdout.splitlines()) if line.startswith("{")))

    return run


def test_stalled_turn_reports_live_hp_and_recovers_without_replaying_action(engine_probe):
    result = engine_probe("stall")
    assert result["actualHp"] == 52
    assert result["isDead"] is False
    for action in ("timeout", "retry", "proceed", "leave", "play"):
        response = result[action]
        assert response["type"] == "error", response
        assert response["error_code"] == "combat_turn_timeout"
        assert response["player"]["hp"] == 52
        assert response["round"] == 3
        assert response["combat_in_progress"] is True
        assert "victory" not in response
        assert "decision" not in response

    # The first retry after recovery exports the resumed state instead of ending it.
    assert result["recovered"]["decision"] == "combat_play"
    assert result["recovered"]["round"] == 3
    assert result["recovered"]["player"]["hp"] == 52
    assert result["nextTurn"]["decision"] == "combat_play"
    assert result["nextTurn"]["round"] == 4


def test_real_death_still_returns_game_over(engine_probe):
    response = engine_probe("death")["result"]
    assert response["decision"] == "game_over"
    assert response["victory"] is False
    assert response["player"]["hp"] == 0
