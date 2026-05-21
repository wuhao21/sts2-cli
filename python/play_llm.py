#!/usr/bin/env python3
"""
Play STS2 using an LLM agent via OpenAI-compatible API.

Usage:
  python3 play_llm.py [--character CHARACTER] [--seed SEED] [--model MODEL] [--verbose]

Examples:
  python3 play_llm.py
  python3 play_llm.py --character Silent --seed myseed --model claude-sonnet-4-6
"""

import argparse
import json
import subprocess
import sys
import os
import time
import traceback
from datetime import datetime

from openai import OpenAI
from game_log import GameLogger


class TeeWriter:
    """Tee stdout to both terminal and a log file."""

    def __init__(self, log_path):
        self._terminal = sys.stdout
        self._log = open(log_path, "w", encoding="utf-8")

    def write(self, msg):
        self._terminal.write(msg)
        self._log.write(msg)
        self._log.flush()

    def flush(self):
        self._terminal.flush()
        self._log.flush()

    def close(self):
        self._log.close()

    @property
    def encoding(self):
        return self._terminal.encoding

# --- Config ---
API_KEY = "sk-18Sd11tZ4CmR1yYGTGL2Sqyot3ZC3pUZ9ocUop6vtbPzz7TB"
BASE_URL = "https://aimux.alibaba-inc.com/v1"
DEFAULT_MODEL = "claude-sonnet-4-6"
VALID_CHARACTERS = ["Ironclad", "Silent", "Defect", "Regent", "Necrobinder"]

SYSTEM_PROMPT = """You are playing Slay the Spire 2, a roguelike deckbuilding card game.

You receive game states and must output ONE action per turn. You have access to recent conversation history for context about the current run.

## Output Format
Line 1: Brief reasoning (1 sentence, Chinese OK)
Line 2: JSON action

Example:
打出防御来挡住即将到来的15点伤害
{"action": "play_card", "args": {"card_index": 2}}

## Decision Types & Actions

### combat_play
Play cards or end turn. Cards have: name, cost, type, target_type, can_play, stats.
- Play a card: {"action": "play_card", "args": {"card_index": N, "target_index": M}}
  - target_index only needed when target_type == "AnyEnemy"
- Use a potion: {"action": "use_potion", "args": {"potion_index": N, "target_index": M}}
- End turn: {"action": "end_turn"}

Strategy tips:
- Play 0-cost cards first (free value)
- Check enemy intents: "Attack" means incoming damage, block accordingly
- Kill low-HP enemies to reduce incoming damage
- Don't block when no attack is incoming — use energy on damage
- Powers are always good early (lasting buffs)

### map_select
Choose next room on the map.
- {"action": "select_map_node", "args": {"col": C, "row": R}}
- Room types: Monster (fight), Elite (hard fight, good reward), RestSite (heal/upgrade), Shop, Treasure, Unknown (random event), Boss

### card_reward
Pick a card after combat, or skip.
- {"action": "select_card_reward", "args": {"card_index": N}}
- {"action": "skip_card_reward"}

### event_choice
Choose an option in a random event.
- {"action": "choose_option", "args": {"option_index": N}}

### rest_site
Choose rest action (heal, smith/upgrade, etc.)
- {"action": "choose_option", "args": {"option_index": N}}

### card_select
Select card(s) from a list (for upgrade, discard, etc.)
- {"action": "select_cards", "args": {"indices": "0"}}  (comma-separated indices)
- {"action": "skip_select"}

### shop
Buy cards or leave.
- {"action": "buy_card", "args": {"card_index": N}}
- {"action": "leave_room"}

### bundle_select
Choose between card bundles.
- {"action": "select_bundle", "args": {"bundle_index": N}}

### game_over
No action needed.

## Important Rules
- Only play cards where can_play == true AND cost <= your current energy
- For AnyEnemy target cards, you MUST provide target_index
- Output ONLY reasoning + JSON, nothing else
"""


def _resolve_description(text, stats):
    """Replace [VarName] placeholders in card/relic/potion descriptions with actual values."""
    if not text or not stats:
        return text or ""
    import re
    # Strip BBCode tags
    text = re.sub(r'\[/?[a-zA-Z_][^\]]*\]', '', text)
    # Resolve {VarName:...} → [VarName]
    text = re.sub(r'\{([^{}:]+):[^{}]*\}', r'[\1]', text)
    text = re.sub(r'\{([^{}]+)\}', r'[\1]', text)
    # Replace [VarName] with stats values (case-insensitive)
    lower_stats = {k.lower(): v for k, v in stats.items()}
    def replacer(m):
        key = m.group(1)
        # Handle plural: [Cards:card|cards]
        if ':' in key and '|' in key:
            var_name = key.split(':')[0]
            val = lower_stats.get(var_name.lower())
            return str(val) if val is not None else m.group(0)
        val = lower_stats.get(key.lower())
        return str(val) if val is not None else m.group(0)
    return re.sub(r'\[([^\]]+)\]', replacer, text)


def _find_dotnet():
    env = os.environ.copy()
    env["DOTNET_ROLL_FORWARD"] = "Major"
    for p in [os.path.expanduser("~/.dotnet-arm64/dotnet"),
              os.path.expanduser("~/.dotnet/dotnet"),
              "/opt/homebrew/bin/dotnet", "dotnet"]:
        try:
            r = subprocess.run([p, "--list-sdks"], capture_output=True, text=True, timeout=5, env=env)
            if r.returncode == 0 and r.stdout.strip():
                return p
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return "dotnet"


class STS2Engine:
    """Manages the headless STS2 subprocess."""

    def __init__(self, verbose=False, log_dir=None):
        self.verbose = verbose
        dotnet = _find_dotnet()
        cli_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        project = os.path.join(cli_dir, "src", "Sts2Headless", "Sts2Headless.csproj")

        game_dir = os.environ.get("STS2_GAME_DIR", os.path.expanduser(
            "~/Library/Application Support/Steam/steamapps/common/"
            "Slay the Spire 2/SlayTheSpire2.app/Contents/Resources/data_sts2_macos_arm64"))
        env = os.environ.copy()
        env["STS2_GAME_DIR"] = game_dir
        env["DOTNET_ROLL_FORWARD"] = "Major"

        # Capture engine stderr to log file
        self._stderr_log = None
        if log_dir:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            stderr_path = os.path.join(log_dir, f"engine_{ts}.log")
            self._stderr_log = open(stderr_path, "w")
            if verbose:
                print(f"Engine stderr -> {stderr_path}")

        self.proc = subprocess.Popen(
            [dotnet, "run", "--no-build", "--project", project],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self._stderr_log or subprocess.PIPE,
            text=True, bufsize=1, cwd=cli_dir, env=env
        )

        ready = self._read()
        if ready.get("type") != "ready":
            raise RuntimeError(f"Engine failed to start: {ready}")
        if verbose:
            print(f"Engine ready: v{ready.get('version', '?')}")

    def _read(self) -> dict:
        while True:
            line = self.proc.stdout.readline().strip()
            if not line:
                # Capture stderr for diagnostics if not already going to a log file
                stderr_snippet = ""
                if not self._stderr_log:
                    try:
                        stderr_out = self.proc.stderr.read()
                        if stderr_out:
                            lines = stderr_out.strip().splitlines()[-10:]
                            stderr_snippet = " | stderr: " + " ".join(lines)
                    except Exception:
                        pass
                return {"type": "error", "message": f"EOF - engine process ended{stderr_snippet}"}
            if line.startswith("{"):
                return json.loads(line)

    def send(self, cmd: dict) -> dict:
        try:
            self.proc.stdin.write(json.dumps(cmd) + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError):
            return self._read()  # will return EOF error with stderr
        return self._read()

    def close(self):
        try:
            self.proc.stdin.write(json.dumps({"cmd": "quit"}) + "\n")
            self.proc.stdin.flush()
        except:
            pass
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except:
            self.proc.kill()
        if self._stderr_log:
            self._stderr_log.close()


class LLMAgent:
    """Calls LLM API to decide actions."""

    def __init__(self, model=DEFAULT_MODEL, verbose=False, history_len=20):
        self.client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
        self.model = model
        self.verbose = verbose
        self.total_tokens = 0
        self.history_len = history_len
        self._history: list[dict] = []
        self._deck: list[str] = []

    def update_deck(self, state: dict):
        """Track current deck from state if available."""
        player = state.get("player", {})
        deck = player.get("deck") if player else None
        if deck:
            self._deck = [c.get("name", "?") for c in deck]

    def decide(self, state: dict, retry=0) -> tuple[dict, str]:
        """Given game state, return (action_dict, raw_llm_text)."""
        self.update_deck(state)
        user_msg = self._format_state(state)

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(self._history[-self.history_len * 2:])
        messages.append({"role": "user", "content": user_msg})

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=300,
                temperature=0.3,
            )
        except Exception as e:
            print(f"  [LLM ERROR] {e}")
            if retry < 8:
                wait = min(2 ** retry, 60)
                time.sleep(wait)
                return self.decide(state, retry + 1)
            return self._fallback(state), ""

        text = resp.choices[0].message.content.strip()
        if resp.usage:
            self.total_tokens += resp.usage.total_tokens

        if self.verbose:
            print(f"  [LLM] {text[:200]}")

        self._history.append({"role": "user", "content": user_msg})
        self._history.append({"role": "assistant", "content": text})

        return self._parse_response(text, state), text

    def _format_state(self, state: dict) -> str:
        """Format game state as concise prompt for the LLM."""
        decision = state.get("decision", "unknown")
        parts = [f"Decision: {decision}"]

        player = state.get("player", {})
        if player:
            parts.append(f"HP: {player.get('hp')}/{player.get('max_hp')} | Gold: {player.get('gold')} | Deck: {player.get('deck_size')} cards")
            relics = player.get("relics", [])
            if relics:
                relic_names = [r.get("name", "?") for r in relics]
                parts.append(f"Relics: {', '.join(relic_names)}")

        ctx = state.get("context", {})
        if ctx:
            parts.append(f"Act {ctx.get('act', '?')} Floor {ctx.get('floor', '?')}")

        if decision == "combat_play":
            energy = state.get("energy", 0)
            max_energy = state.get("max_energy", 3)
            rnd = state.get("round", 1)
            draw = state.get("draw_pile_count", "?")
            discard = state.get("discard_pile_count", "?")
            parts.append(f"Round {rnd} | Energy: {energy}/{max_energy} | Draw pile: {draw} | Discard pile: {discard}")

            # Player block & powers
            player_block = player.get("block", 0)
            if player_block > 0:
                parts.append(f"Player block: {player_block}")
            ppowers = state.get("player_powers") or []
            if ppowers:
                pw_strs = [f"{pw.get('name','?')} {pw.get('amount','')}" for pw in ppowers]
                parts.append(f"Buffs/Debuffs: {', '.join(pw_strs)}")

            # Stars (Regent)
            stars = state.get("stars")
            if stars is not None:
                parts.append(f"Stars: {stars}")

            # Osty (Necrobinder)
            osty = state.get("osty", {})
            if osty and osty.get("alive"):
                parts.append(f"Osty: HP={osty.get('hp')}/{osty.get('max_hp')} Block={osty.get('block',0)} ATK={osty.get('attack',0)}")

            # Orbs (Defect)
            orbs = state.get("orbs")
            if orbs:
                orb_strs = [f"{o.get('name', o.get('type','?'))}(passive={o.get('passive',0)},evoke={o.get('evoke',0)})" for o in orbs]
                parts.append(f"Orbs [{len(orbs)}/{state.get('orb_slots', len(orbs))}]: {', '.join(orb_strs)}")

            # Enemies
            enemies = state.get("enemies", [])
            enemy_strs = []
            for e in enemies:
                intents = e.get("intents", [])
                intent_parts = []
                for i in intents:
                    itype = i.get("type", "")
                    dmg = i.get("damage")
                    hits = i.get("hits")
                    if itype == "Attack":
                        if dmg is not None:
                            intent_parts.append(f"Attack {dmg}x{hits}" if hits and hits > 1 else f"Attack {dmg}")
                        else:
                            intent_parts.append("Attack ?")
                    elif itype == "Defend":
                        intent_parts.append("Defend")
                    elif itype in ("Buff", "Heal"):
                        intent_parts.append(itype)
                    elif itype == "Debuff":
                        intent_parts.append("Debuff")
                    elif itype:
                        intent_parts.append(itype)
                intent_str = ", ".join(intent_parts) if intent_parts else "Unknown"
                blk = e.get("block", 0)
                powers = e.get("powers") or []
                pw_str = ""
                if powers:
                    pw_str = " | Powers: " + ", ".join(f"{pw.get('name','?')} {pw.get('amount','')}" for pw in powers)
                enemy_strs.append(f"  [{e.get('index',0)}] {e['name']} HP={e['hp']}/{e.get('max_hp','?')}"
                                  + (f" Block={blk}" if blk else "")
                                  + f" | Intent: {intent_str}{pw_str}")
            parts.append("Enemies:\n" + "\n".join(enemy_strs))

            # Hand
            hand = state.get("hand", [])
            hand_strs = []
            for card in hand:
                playable = "●" if card.get("can_play") else "○"
                cost = card.get("cost", 0)
                name = card.get("name", "?")
                ctype = card.get("type", "?")
                target = card.get("target_type", "")
                stats = card.get("stats", {})
                desc = _resolve_description(card.get("description", ""), stats)

                stat_parts = []
                if stats.get("damage"):
                    stat_parts.append(f"{stats['damage']}dmg")
                if stats.get("block"):
                    stat_parts.append(f"{stats['block']}blk")
                if stats.get("magic_number"):
                    stat_parts.append(f"magic={stats['magic_number']}")
                stat_str = " " + " ".join(stat_parts) if stat_parts else ""

                target_str = " -> enemy" if target == "AnyEnemy" else ""
                keywords = card.get("keywords") or []
                kw_str = ""
                if keywords:
                    kw_str = " [" + ", ".join(str(k) for k in keywords if k != "None") + "]"

                s = f"  {playable} [{card['index']}] {name} ({cost}){stat_str}{target_str}{kw_str}"
                if desc:
                    s += f"\n      {desc}"
                hand_strs.append(s)
            parts.append("Hand:\n" + "\n".join(hand_strs))

            # Potions
            potions = state.get("potions", [])
            if potions:
                pot_strs = []
                for p in potions:
                    target = p.get("target_type", "")
                    target_str = " -> enemy" if "Enemy" in target else ""
                    p_desc = _resolve_description(p.get("description", ""), p.get("vars", {}))
                    s = f"  [P{p['index']}] {p['name']}{target_str}"
                    if p_desc:
                        s += f"\n      {p_desc}"
                    pot_strs.append(s)
                parts.append("Potions:\n" + "\n".join(pot_strs))

        elif decision == "map_select":
            choices = state.get("choices", [])
            choice_strs = [f"({c['col']},{c['row']}) {c['type']}" for c in choices]
            parts.append("Choices: " + " | ".join(choice_strs))

        elif decision == "card_reward":
            cards = state.get("cards", [])
            card_strs = []
            for c in cards:
                stats = c.get("stats", {})
                desc = _resolve_description(c.get("description", ""), stats)
                stat_parts = []
                if stats.get("damage"):
                    stat_parts.append(f"{stats['damage']}dmg")
                if stats.get("block"):
                    stat_parts.append(f"{stats['block']}blk")
                stat_str = " " + " ".join(stat_parts) if stat_parts else ""
                s = f"  [{c['index']}] {c['name']} ({c.get('cost','?')}) {c['type']}{stat_str}"
                if desc:
                    s += f"\n      {desc}"
                card_strs.append(s)
            parts.append("Cards offered:\n" + "\n".join(card_strs))
            if self._deck:
                parts.append(f"Current deck ({len(self._deck)} cards): {', '.join(self._deck)}")

        elif decision == "event_choice":
            options = state.get("options", [])
            opt_strs = [f"[{o['index']}] {o.get('title', o.get('name', '?'))} locked={o.get('is_locked', False)}" for o in options]
            parts.append("Options:\n" + "\n".join(opt_strs))

        elif decision == "rest_site":
            options = state.get("options", [])
            opt_strs = [f"[{o['index']}] {o.get('option_id', '?')} enabled={o.get('is_enabled', True)}" for o in options]
            parts.append("Options: " + " | ".join(opt_strs))

        elif decision == "card_select":
            cards = state.get("cards", [])
            card_strs = [f"[{c['index']}] {c['name']}" for c in cards]
            n = state.get("min_select", 1)
            parts.append(f"Select {n} card(s):\n" + "\n".join(card_strs))

        elif decision == "shop":
            gold = player.get("gold", 0)
            card_strs = []
            for c in state.get("cards", []):
                if not c.get("is_stocked"):
                    continue
                stats = c.get("stats", {})
                desc = _resolve_description(c.get("description", ""), stats)
                price = c.get("cost", "?")
                sale = " SALE" if c.get("on_sale") else ""
                s = f"  [{c['index']}] {c['name']} ({c.get('card_cost','?')}) {c.get('type','?')} — {price}g{sale}"
                if desc:
                    s += f"\n      {desc}"
                card_strs.append(s)
            parts.append("Shop cards:\n" + "\n".join(card_strs))

            relic_strs = []
            for r in state.get("relics", []):
                if not r.get("is_stocked"):
                    continue
                r_desc = _resolve_description(r.get("description", ""), r.get("vars", {}))
                s = f"  [r{r['index']}] {r['name']} — {r.get('cost','?')}g"
                if r_desc:
                    s += f"\n      {r_desc}"
                relic_strs.append(s)
            if relic_strs:
                parts.append("Shop relics:\n" + "\n".join(relic_strs))

            pot_strs = []
            for p in state.get("potions", []):
                if not p.get("is_stocked"):
                    continue
                p_desc = _resolve_description(p.get("description", ""), p.get("vars", {}))
                s = f"  [p{p['index']}] {p['name']} — {p.get('cost','?')}g"
                if p_desc:
                    s += f"\n      {p_desc}"
                pot_strs.append(s)
            if pot_strs:
                parts.append("Shop potions:\n" + "\n".join(pot_strs))

            parts.append(f"Card removal cost: {state.get('card_removal_cost', '?')}g")
            if self._deck:
                parts.append(f"Current deck ({len(self._deck)} cards): {', '.join(self._deck)}")

        elif decision == "bundle_select":
            bundles = state.get("bundles", [])
            for i, b in enumerate(bundles):
                cards = b.get("cards", [])
                names = [c.get("name", "?") for c in cards]
                parts.append(f"Bundle [{i}]: {', '.join(names)}")
            if self._deck:
                parts.append(f"Current deck ({len(self._deck)} cards): {', '.join(self._deck)}")

        return "\n".join(parts)

    def _parse_response(self, text: str, state: dict) -> dict:
        """Extract JSON action from LLM response."""
        lines = text.strip().split("\n")
        for line in reversed(lines):
            line = line.strip()
            if line.startswith("{"):
                try:
                    parsed = json.loads(line)
                    if "action" in parsed:
                        return parsed
                except json.JSONDecodeError:
                    continue

        # Try to find JSON anywhere in text
        import re
        matches = re.findall(r'\{[^{}]+\}', text)
        for m in reversed(matches):
            try:
                parsed = json.loads(m)
                if "action" in parsed:
                    return parsed
            except json.JSONDecodeError:
                continue

        print(f"  [PARSE FAIL] Could not extract action from: {text[:100]}")
        return self._fallback(state)

    def _fallback(self, state: dict) -> dict:
        """Simple fallback when LLM fails."""
        decision = state.get("decision", "")

        if decision == "combat_play":
            hand = state.get("hand", [])
            energy = state.get("energy", 0)
            enemies = state.get("enemies", [])
            for c in hand:
                if c.get("can_play") and c.get("cost", 99) <= energy:
                    args = {"card_index": c["index"]}
                    if c.get("target_type") == "AnyEnemy" and enemies:
                        args["target_index"] = 0
                    return {"action": "play_card", "args": args}
            return {"action": "end_turn"}

        elif decision == "map_select":
            choices = state.get("choices", [])
            if choices:
                return {"action": "select_map_node", "args": {"col": choices[0]["col"], "row": choices[0]["row"]}}

        elif decision == "card_reward":
            return {"action": "skip_card_reward"}

        elif decision == "event_choice":
            options = state.get("options", [])
            opt = next((o for o in options if not o.get("is_locked")), options[0] if options else None)
            if opt:
                return {"action": "choose_option", "args": {"option_index": opt["index"]}}

        elif decision == "rest_site":
            return {"action": "choose_option", "args": {"option_index": 0}}

        elif decision == "card_select":
            return {"action": "select_cards", "args": {"indices": "0"}}

        elif decision == "shop":
            return {"action": "leave_room"}

        elif decision == "bundle_select":
            return {"action": "select_bundle", "args": {"bundle_index": 0}}

        return {"action": "proceed"}


def play_run(character: str, seed: str, model: str, verbose: bool):
    """Play one full run with LLM agent."""
    # Setup logging
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
    os.makedirs(log_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Terminal output tee (captures everything printed to stdout)
    tee_path = os.path.join(log_dir, f"llm_{character}_{seed}_{ts}.log")
    tee = TeeWriter(tee_path)
    sys.stdout = tee

    # Structured game log (same as play.py)
    logger = GameLogger(character, seed, enabled=True)

    print(f"Character: {character} | Seed: {seed} | Model: {model}")
    print(f"Terminal log: {tee_path}")
    if logger.path:
        print(f"Game log: {logger.path}")
    print("=" * 60)

    engine = STS2Engine(verbose=verbose, log_dir=log_dir)
    agent = LLMAgent(model=model, verbose=verbose)

    try:
        state = engine.send({"cmd": "start_run", "character": character, "seed": seed})
        logger.log_state(state)

        step = 0
        max_steps = 500
        stuck_count = 0
        last_state_key = ""

        while step < max_steps:
            step += 1
            decision = state.get("decision", "")

            if state.get("type") == "error":
                print(f"  [ENGINE ERROR] {state.get('message', '')[:80]}")
                cmd = {"cmd": "action", "action": "proceed"}
                logger.log_action(cmd)
                state = engine.send(cmd)
                logger.log_state(state)
                if state.get("type") == "error":
                    cmd = {"cmd": "action", "action": "leave_room"}
                    logger.log_action(cmd)
                    state = engine.send(cmd)
                    logger.log_state(state)
                continue

            if decision == "game_over":
                victory = state.get("victory", False)
                player = state.get("player", {})
                ctx = state.get("context", {})
                print(f"\n{'=' * 40}")
                print(f"{'VICTORY!' if victory else 'DEFEAT'}")
                print(f"Act {ctx.get('act')} Floor {ctx.get('floor')}")
                print(f"HP: {player.get('hp')}/{player.get('max_hp')}")
                print(f"Steps: {step} | LLM tokens: {agent.total_tokens}")
                print(f"{'=' * 40}")
                return victory

            # Stuck detection
            hand_len = len(state.get("hand", []))
            enemy_hp = sum(e.get("hp", 0) for e in state.get("enemies", []))
            state_key = f"{decision}:{state.get('round')}:{state.get('player',{}).get('hp')}:{hand_len}:{enemy_hp}"
            if state_key == last_state_key:
                stuck_count += 1
                if stuck_count > 15:
                    print(f"  [STUCK] Same state {stuck_count} times, forcing end_turn/proceed")
                    cmd = {"cmd": "action", "action": "end_turn"}
                    logger.log_action(cmd)
                    state = engine.send(cmd)
                    logger.log_state(state)
                    if state.get("type") == "error":
                        cmd = {"cmd": "action", "action": "proceed"}
                        logger.log_action(cmd)
                        state = engine.send(cmd)
                        logger.log_state(state)
                    stuck_count = 0
                    continue
            else:
                stuck_count = 0
                last_state_key = state_key

            # Status line
            player = state.get("player", {})
            ctx = state.get("context", {})
            hp_str = f"HP={player.get('hp','?')}/{player.get('max_hp','?')}" if player else ""
            loc_str = f"A{ctx.get('act','?')}F{ctx.get('floor','?')}" if ctx else ""
            print(f"\n[Step {step}] {decision} | {loc_str} {hp_str}")

            # Ask LLM
            action_dict, _ = agent.decide(state)

            act_name = action_dict.get("action", "?")
            act_args = action_dict.get("args", {})
            print(f"  -> {act_name} {act_args}")

            # Send to engine
            cmd = {"cmd": "action", "action": act_name}
            if act_args:
                cmd["args"] = act_args
            logger.log_action(cmd)
            state = engine.send(cmd)
            logger.log_state(state)

        print(f"\n[TIMEOUT] Reached {max_steps} steps")
        return False

    except Exception as e:
        print(f"\n[EXCEPTION] {e}")
        traceback.print_exc()
        return False

    finally:
        engine.close()
        logger.close()
        sys.stdout = tee._terminal
        tee.close()
        if logger.path:
            print(f"Game log: {logger.path}")
        print(f"Terminal log: {tee_path}")


def main():
    parser = argparse.ArgumentParser(description="Play STS2 with an LLM agent")
    parser.add_argument("--character", "-c", default="Ironclad", choices=VALID_CHARACTERS)
    parser.add_argument("--seed", "-s", default=None)
    parser.add_argument("--model", "-m", default=DEFAULT_MODEL)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    seed = args.seed or f"llm_{int(time.time())}"
    play_run(args.character, seed, args.model, args.verbose)


if __name__ == "__main__":
    main()
