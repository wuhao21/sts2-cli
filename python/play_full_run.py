#!/usr/bin/env python3
"""
Play a full STS2 run using the headless simulator with a random agent.

Usage:
  python3 play_full_run.py <num_runs> [character]

Arguments:
  num_runs    Positive integer: number of runs to play
  character   One of: Ironclad, Silent, Defect, Regent, Necrobinder (default: Ironclad)

Examples:
  python3 play_full_run.py 5
  python3 play_full_run.py 3 Silent
"""

import argparse
import json
import subprocess
import sys
import random
import os
import queue
import threading
from game_log import GameLogger

VALID_CHARACTERS = ["Ironclad", "Silent", "Defect", "Regent", "Necrobinder"]

def _find_dotnet():
    for p in [os.path.expanduser("~/.dotnet-arm64/dotnet"),
              os.path.expanduser("~/.dotnet/dotnet"), "dotnet"]:
        try:
            if subprocess.run([p, "--version"], capture_output=True, timeout=5).returncode == 0:
                return p
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return "dotnet"

DOTNET = _find_dotnet()
PROJECT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "src", "Sts2Headless", "Sts2Headless.csproj")


def play_run(seed: str, character: str = "Ironclad", verbose: bool = True, log: bool = True):
    """Play a complete run and return the result."""
    rng = random.Random(seed)
    logger = GameLogger(character, seed, enabled=log)
    proc = subprocess.Popen(
        [DOTNET, "run", "--no-build", "--project", PROJECT],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL if not verbose else None,
        text=True,
        bufsize=1,
    )

    responses = queue.Queue()

    def collect_output():
        for line in proc.stdout:
            responses.put(line)
        responses.put(None)

    threading.Thread(target=collect_output, daemon=True).start()

    def read_json_line() -> dict:
        """Bound response waits so a deadlocked engine fails the regression."""
        while True:
            try:
                line = responses.get(timeout=30)
            except queue.Empty:
                raise TimeoutError("No simulator response within 30 seconds") from None
            if line is None:
                raise RuntimeError("No response from simulator (EOF)")
            if line.startswith("{"):
                return json.loads(line)
            if verbose:
                print(f"  [skip] {line.strip()[:120]}")

    def send(cmd: dict) -> dict:
        line = json.dumps(cmd)
        if verbose:
            print(f"  > {line[:200]}")
        logger.log_action(cmd)
        proc.stdin.write(line + "\n")
        proc.stdin.flush()
        resp = read_json_line()
        logger.log_state(resp)
        if verbose:
            rtype = resp.get("type", "?")
            decision = resp.get("decision", "")
            if rtype == "decision":
                player = resp.get("player", {})
                hp = player.get("hp", "?")
                max_hp = player.get("max_hp", "?")
                gold = player.get("gold", "?")
                act = resp.get("act", "?")
                floor = resp.get("floor", "?")
                print(f"  < {rtype}/{decision} act={act} floor={floor} hp={hp}/{max_hp} gold={gold}")
            else:
                print(f"  < {json.dumps(resp)[:200]}")
        return resp

    step = 0
    try:
        # Read ready message (may need to skip build warnings)
        ready = read_json_line()
        if ready.get("type") != "ready":
            print(f"  Unexpected initial response: {ready}")
            return {"victory": False, "seed": seed, "error": "bad_init"}
        if verbose:
            print(f"Connected: {ready}")

        # Start run
        state = send({"cmd": "start_run", "character": character, "seed": seed})

        step = 0
        max_steps = 2000  # Safety limit
        stuck_count = 0
        last_state_key = None

        while step < max_steps:
            step += 1

            if state.get("type") == "error":
                print(f"  ERROR: {state.get('message', 'unknown')}")
                raise RuntimeError(state.get("message", "Simulator error"))

            decision = state.get("decision", "")

            # Stuck detection — use comprehensive state key
            hand_len = len(state.get("hand", []))
            enemy_hp = sum(e.get("hp", 0) for e in state.get("enemies", []))
            energy = state.get("energy", 0)
            state_key = f"{decision}:{state.get('round')}:{state.get('player',{}).get('hp')}:{hand_len}:{enemy_hp}:{energy}"
            if state_key == last_state_key:
                stuck_count += 1
                if stuck_count > 20:
                    print(f"  STUCK after {step} steps, forcing quit")
                    return {"victory": False, "seed": seed, "steps": step, "error": "stuck",
                            "act": state.get("act"), "floor": state.get("floor"),
                            "hp": state.get("player", {}).get("hp"),
                            "max_hp": state.get("player", {}).get("max_hp")}
            else:
                stuck_count = 0
                last_state_key = state_key

            if decision == "game_over":
                victory = state.get("victory", False)
                player = state.get("player", {})
                print(f"\n{'VICTORY' if victory else 'DEFEAT'} at act {state.get('act')}, "
                      f"floor {state.get('floor')} "
                      f"(HP: {player.get('hp')}/{player.get('max_hp')}, "
                      f"Gold: {player.get('gold')}, "
                      f"Deck: {player.get('deck_size')} cards)")
                return {
                    "victory": victory,
                    "completed": True,
                    "seed": seed,
                    "steps": step,
                    "act": state.get("act"),
                    "floor": state.get("floor"),
                    "hp": player.get("hp"),
                    "max_hp": player.get("max_hp"),
                }

            elif decision == "map_select":
                choices = state.get("choices", [])
                if not choices:
                    print("  No map choices available!")
                    break
                # Random selection
                choice = rng.choice(choices)
                state = send({
                    "cmd": "action",
                    "action": "select_map_node",
                    "args": {"col": choice["col"], "row": choice["row"]}
                })

            elif decision == "combat_play":
                hand = state.get("hand", [])
                energy = state.get("energy", 0)
                enemies = state.get("enemies", [])

                # Simple strategy: play playable cards until out of energy
                playable = [c for c in hand if c.get("can_play", False)
                           and (c.get("cost", 0) <= energy)]

                if playable:
                    card = playable[0]
                    args = {"card_index": card["index"]}
                    # If card needs a target, pick first enemy
                    if card.get("target_type") == "AnyEnemy" and enemies:
                        args["target_index"] = 0
                    state = send({
                        "cmd": "action",
                        "action": "play_card",
                        "args": args
                    })
                else:
                    # End turn - retry a few times if we get "Not in play phase"
                    for retry in range(5):
                        state = send({
                            "cmd": "action",
                            "action": "end_turn"
                        })
                        if state.get("type") != "error":
                            break
                        if state.get("error_code") == "combat_turn_timeout":
                            break
                        import time
                        time.sleep(0.5)

            elif decision == "event_choice":
                options = state.get("options", [])
                if options:
                    # Pick first unlocked option
                    choice = next((o for o in options if not o.get("is_locked")), options[0])
                    state = send({
                        "cmd": "action",
                        "action": "choose_option",
                        "args": {"option_index": choice["index"]}
                    })
                else:
                    state = send({"cmd": "action", "action": "leave_room"})

            elif decision == "rest_site":
                options = state.get("options", [])
                # Prefer heal (HEAL), then smith
                enabled = [o for o in options if o.get("is_enabled", True)]
                heal = next((o for o in enabled if o.get("option_id") == "HEAL"), None)
                choice = heal or (enabled[0] if enabled else None)
                if choice:
                    state = send({
                        "cmd": "action",
                        "action": "choose_option",
                        "args": {"option_index": choice["index"]}
                    })
                else:
                    state = send({"cmd": "action", "action": "leave_room"})

            elif decision == "card_reward":
                # Pick the first card offered
                cards = state.get("cards", [])
                if cards:
                    state = send({
                        "cmd": "action",
                        "action": "select_card_reward",
                        "args": {"card_index": 0}
                    })
                else:
                    state = send({"cmd": "action", "action": "skip_card_reward"})

            elif decision == "bundle_select":
                state = send({"cmd": "action", "action": "select_bundle",
                             "args": {"bundle_index": 0}})

            elif decision == "card_select":
                # Auto-select first card
                cards = state.get("cards", [])
                if cards:
                    state = send({"cmd": "action", "action": "select_cards",
                                 "args": {"indices": "0"}})
                else:
                    state = send({"cmd": "action", "action": "skip_select"})

            elif decision == "shop":
                state = send({"cmd": "action", "action": "leave_room"})

            elif decision == "unknown":
                state = send({"cmd": "action", "action": "proceed"})

            else:
                raise RuntimeError(f"Unsupported decision: {decision!r}")

        print(f"  Reached max steps ({max_steps})")
        return {"victory": False, "seed": seed, "steps": step, "timeout": True}

    except Exception as e:
        print(f"  EXCEPTION: {e}")
        return {"victory": False, "seed": seed, "steps": step, "error": str(e)}

    finally:
        logger.close()
        if logger.path:
            print(f"  [log] Saved to {logger.path}")
        try:
            proc.stdin.write(json.dumps({"cmd": "quit"}) + "\n")
            proc.stdin.flush()
        except:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except:
            proc.kill()


def main():
    parser = argparse.ArgumentParser(
        description="Play full STS2 runs using the headless simulator with a random agent.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Valid characters: " + ", ".join(VALID_CHARACTERS),
    )
    parser.add_argument("num_runs", type=int, help="Number of runs to play (must be positive)")
    parser.add_argument("character", nargs="?", default="Ironclad",
                        choices=VALID_CHARACTERS, metavar="character",
                        help=f"Character to play as (default: Ironclad). Choices: {', '.join(VALID_CHARACTERS)}")
    args = parser.parse_args()

    if args.num_runs <= 0:
        parser.error(f"num_runs must be a positive integer, got {args.num_runs}")

    num_runs = args.num_runs
    character = args.character

    print(f"Playing {num_runs} runs as {character}")
    print("=" * 60)

    results = []
    for i in range(num_runs):
        seed = f"run_{i+1}"
        print(f"\n--- Run {i+1}/{num_runs} (seed: {seed}) ---")
        result = play_run(seed, character, verbose=True)
        results.append(result)
        print()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    wins = sum(1 for r in results if r and r.get("victory"))
    completed = sum(1 for r in results if r and r.get("completed"))
    for i, r in enumerate(results):
        if r:
            status = "WIN" if r.get("victory") else ("LOSS" if r.get("completed") else "ERROR")
            print(f"  Run {i+1}: {status} | seed={r.get('seed')} steps={r.get('steps')} "
                  f"act={r.get('act')} floor={r.get('floor')}")
    print(f"\nWins: {wins}/{num_runs}, Completed: {completed}/{num_runs}")
    return 0 if completed == num_runs else 1


if __name__ == "__main__":
    sys.exit(main())
