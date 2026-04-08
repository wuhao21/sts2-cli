"""Pytest fixtures: Game process wrapper for unit tests."""

import json
import os
import shutil
import subprocess
import pytest

DOTNET = os.path.expanduser("~/.dotnet-arm64/dotnet")
if not os.path.isfile(DOTNET):
    DOTNET = shutil.which("dotnet") or DOTNET
PROJECT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "src", "Sts2Headless", "Sts2Headless.csproj")


class Game:
    """Wraps the headless C# process for testing."""

    def __init__(self):
        env = os.environ.copy()
        env.setdefault("STS2_GAME_DIR",
                       os.path.expanduser("~/Library/Application Support/Steam/steamapps/common/"
                                          "Slay the Spire 2/SlayTheSpire2.app/Contents/Resources/"
                                          "data_sts2_macos_arm64"))
        self.proc = subprocess.Popen(
            [DOTNET, "run", "--no-build", "--project", PROJECT],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1, env=env,
        )
        ready = self._read()
        assert ready.get("type") == "ready", f"Expected ready, got: {ready}"

    def _read(self):
        while True:
            line = self.proc.stdout.readline().strip()
            if not line:
                raise RuntimeError("EOF from game process")
            if line.startswith("{"):
                return json.loads(line)

    def send(self, cmd):
        self.proc.stdin.write(json.dumps(cmd) + "\n")
        self.proc.stdin.flush()
        return self._read()

    def start(self, character="Ironclad", seed="test", ascension=0, lang="en"):
        return self.send({"cmd": "start_run", "character": character,
                          "seed": seed, "ascension": ascension, "lang": lang})

    def act(self, action, **args):
        cmd = {"cmd": "action", "action": action}
        if args:
            cmd["args"] = args
        return self.send(cmd)

    def get_map(self):
        return self.send({"cmd": "get_map"})

    def set_player(self, **kwargs):
        cmd = {"cmd": "set_player", **kwargs}
        return self.send(cmd)

    def enter_room(self, room_type, **kwargs):
        cmd = {"cmd": "enter_room", "type": room_type, **kwargs}
        return self.send(cmd)

    def set_draw_order(self, cards):
        return self.send({"cmd": "set_draw_order", "cards": cards})

    def console(self, input_text):
        return self.send({"cmd": "console", "input": input_text})

    def close(self):
        try:
            self.proc.stdin.write('{"cmd":"quit"}\n')
            self.proc.stdin.flush()
        except Exception:
            pass
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()

    # --- Auto-play helpers ---

    def auto_combat(self, state):
        """Play one card or end turn."""
        hand = state.get("hand", [])
        energy = state.get("energy", 0)
        playable = [c for c in hand if c.get("can_play") and c.get("cost", 99) <= energy]
        if playable:
            card = playable[0]
            args = {"card_index": card["index"]}
            if card.get("target_type") == "AnyEnemy":
                enemies = state.get("enemies", [])
                if enemies:
                    args["target_index"] = enemies[0]["index"]
            return self.act("play_card", **args)
        return self.act("end_turn")

    def auto_play_combat(self, state, max_steps=300):
        """Auto-play combat until it ends."""
        for _ in range(max_steps):
            if state.get("decision") != "combat_play":
                return state
            state = self.auto_combat(state)
        raise RuntimeError("Combat did not end")

    def skip_neow(self, state):
        """Skip the Neow event and all follow-up rewards until map_select."""
        for _ in range(20):
            dec = state.get("decision", "")
            if dec == "map_select":
                return state
            if dec == "event_choice":
                opts = [o for o in state["options"] if not o.get("is_locked")]
                state = self.act("choose_option", option_index=opts[0]["index"])
            elif dec == "card_reward":
                state = self.act("skip_card_reward")
            elif dec == "bundle_select":
                state = self.act("select_bundle", bundle_index=0)
            elif dec == "card_select":
                if state.get("min_select", 0) == 0:
                    state = self.act("skip_select")
                else:
                    state = self.act("select_cards", indices="0")
            else:
                state = self.act("proceed")
        return state


@pytest.fixture
def game():
    """Each test gets an independent game process."""
    g = Game()
    yield g
    g.close()
