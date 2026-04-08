"""Tests for combat scenarios."""
import pytest


def _combat_signature(state):
    enemies = tuple(
        (enemy.get("name"), enemy.get("hp"), enemy.get("block", 0))
        for enemy in state.get("enemies", [])
    )
    return (
        state.get("decision"),
        state.get("round"),
        state.get("energy"),
        len(state.get("hand", [])),
        enemies,
        state.get("player", {}).get("hp"),
    )


def _step_autoish_run(game, state):
    decision = state.get("decision")

    if decision == "map_select":
        choices = state.get("choices", [])
        assert choices, "Expected at least one map choice"
        player = state.get("player", {})
        hp_ratio = player.get("hp", 1) / max(player.get("max_hp", 1), 1)
        if hp_ratio < 0.4:
            pick = next((choice for choice in choices if choice["type"] == "RestSite"), choices[0])
        else:
            pick = choices[0]
        return game.act("select_map_node", col=pick["col"], row=pick["row"])

    if decision == "event_choice":
        options = [option for option in state["options"] if not option.get("is_locked")]
        return game.act("choose_option", option_index=options[0]["index"])

    if decision == "card_reward":
        return game.act("select_card_reward", card_index=0)

    if decision == "bundle_select":
        return game.act("select_bundle", bundle_index=0)

    if decision == "card_select":
        if state.get("min_select", 0) == 0:
            return game.act("skip_select")
        return game.act("select_cards", indices="0")

    if decision == "rest_site":
        options = [option for option in state["options"] if option.get("is_enabled", True)]
        heal = next((option for option in options if option.get("option_id") == "HEAL"), None)
        pick = heal or options[0]
        return game.act("choose_option", option_index=pick["index"])

    if decision == "shop":
        return game.act("leave_room")

    return game.act("proceed")


def _play_without_repeating_identical_combat_state(game, state, *, max_steps=120, max_repeats=2):
    repeats = 0
    last_signature = None

    for _ in range(max_steps):
        if state.get("decision") != "combat_play":
            return state

        signature = _combat_signature(state)
        if signature == last_signature:
            repeats += 1
        else:
            repeats = 0
            last_signature = signature

        assert repeats < max_repeats, f"Combat state repeated without progress: {signature}"

        hand = state.get("hand", [])
        energy = state.get("energy", 0)
        playable = [card for card in hand if card.get("can_play") and card.get("cost", 99) <= energy]
        if playable:
            card = playable[0]
            args = {"card_index": card["index"]}
            if card.get("target_type") == "AnyEnemy" and state.get("enemies"):
                args["target_index"] = state["enemies"][0]["index"]
            state = game.act("play_card", **args)
        else:
            state = game.act("end_turn")

    pytest.fail(f"Combat did not resolve within {max_steps} steps")


def _advance_to_nibbit(game):
    return _advance_to_enemy(game, character="Silent", seed="reward_probe_1", enemy_name="Nibbit")


def _advance_to_enemy(game, *, character, seed, enemy_name, max_steps=250):
    state = game.start(character=character, seed=seed)
    state = game.skip_neow(state)

    for _ in range(max_steps):
        if state.get("decision") == "combat_play":
            enemy_names = {enemy.get("name") for enemy in state.get("enemies", [])}
            if enemy_name in enemy_names:
                return state
            state = _play_without_repeating_identical_combat_state(game, state, max_steps=80)
            continue

        state = _step_autoish_run(game, state)

    pytest.fail(f"Did not reach the {enemy_name} combat for seed {seed}")


class TestCombatStructure:
    def test_combat_play_fields(self, game):
        state = game.start(seed="cs1")
        game.skip_neow(state)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        assert state["decision"] == "combat_play"
        for key in ("round", "energy", "max_energy", "hand", "enemies",
                    "player", "draw_pile_count", "discard_pile_count", "player_powers"):
            assert key in state, f"Missing: {key}"

    def test_card_fields(self, game):
        state = game.start(seed="cs2")
        game.skip_neow(state)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        for card in state["hand"]:
            assert isinstance(card["name"], str)
            assert "cost" in card
            assert "can_play" in card
            assert card["type"] in ("Attack", "Skill", "Power", "Status", "Curse")

    def test_enemy_fields(self, game):
        state = game.start(seed="cs3")
        game.skip_neow(state)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        for e in state["enemies"]:
            assert isinstance(e["name"], str)
            assert e["hp"] > 0
            assert e["max_hp"] > 0
            assert "block" in e


class TestPlayCards:
    def test_play_card_costs_energy(self, game):
        state = game.start(seed="cp1")
        game.skip_neow(state)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        energy_before = state["energy"]
        playable = [c for c in state["hand"] if c.get("can_play") and c["cost"] <= energy_before]
        assert playable
        card = playable[0]
        args = {"card_index": card["index"]}
        if card.get("target_type") == "AnyEnemy":
            args["target_index"] = state["enemies"][0]["index"]
        state = game.act("play_card", **args)
        if state["decision"] == "combat_play":
            assert state["energy"] == energy_before - card["cost"]

    def test_play_attack_reduces_enemy_hp(self, game):
        state = game.start(seed="cp2")
        game.skip_neow(state)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        target = state["enemies"][0]
        hp_before = target["hp"]
        attacks = [c for c in state["hand"] if c.get("can_play") and c["type"] == "Attack"
                   and c["cost"] <= state["energy"]]
        if not attacks:
            pytest.skip("No attacks in hand")
        card = attacks[0]
        args = {"card_index": card["index"]}
        if card.get("target_type") == "AnyEnemy":
            args["target_index"] = target["index"]
        state = game.act("play_card", **args)
        if state["decision"] == "combat_play":
            new_target = next((e for e in state["enemies"] if e["index"] == target["index"]), None)
            if new_target and target.get("block", 0) == 0:
                assert new_target["hp"] < hp_before

    def test_play_defend_adds_block(self, game):
        state = game.start(seed="cp3")
        game.skip_neow(state)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        block_before = state["player"].get("block", 0)
        defends = [c for c in state["hand"] if c.get("can_play") and c["type"] == "Skill"
                   and c["cost"] <= state["energy"]]
        if not defends:
            pytest.skip("No skill cards")
        state = game.act("play_card", card_index=defends[0]["index"])
        if state["decision"] == "combat_play":
            assert state["player"].get("block", 0) >= block_before


class TestTurnFlow:
    def test_end_turn_advances_round(self, game):
        state = game.start(seed="tf1")
        game.skip_neow(state)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        rnd = state["round"]
        state = game.act("end_turn")
        if state["decision"] == "combat_play":
            assert state["round"] == rnd + 1

    def test_end_turn_resets_energy(self, game):
        state = game.start(seed="tf2")
        game.skip_neow(state)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        max_e = state["max_energy"]
        state = game.act("end_turn")
        if state["decision"] == "combat_play":
            assert state["energy"] == max_e

    def test_end_turn_draws_new_hand(self, game):
        state = game.start(seed="tf3")
        game.skip_neow(state)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        state = game.act("end_turn")
        if state["decision"] == "combat_play":
            assert len(state["hand"]) > 0


class TestCombatEnd:
    def test_win_combat_leads_to_reward(self, game):
        state = game.start(seed="cw1")
        game.skip_neow(state)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        state = game.auto_play_combat(state)
        assert state["decision"] in ("card_reward", "map_select", "card_select", "bundle_select")

    def test_player_powers_after_enemy_debuff(self, game):
        """Shrinker Beetle applies Shrink debuff to player after its turn."""
        state = game.start(seed="ep1")
        game.skip_neow(state)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        # End turn so beetle acts (applies Shrink to player)
        state = game.act("end_turn")
        if state["decision"] == "combat_play":
            pp = state.get("player_powers") or []
            assert len(pp) > 0, "Expected player debuff after Shrinker Beetle turn"
            for pw in pp:
                assert "name" in pw
                assert "amount" in pw
                assert "description" in pw


class TestCombatEdgeCases:
    def test_exhaust_all_and_end_turn(self, game):
        state = game.start(seed="ce1")
        game.skip_neow(state)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        for _ in range(20):
            if state.get("decision") != "combat_play":
                break
            playable = [c for c in state["hand"] if c.get("can_play") and c["cost"] <= state["energy"]]
            if not playable:
                break
            card = playable[0]
            args = {"card_index": card["index"]}
            if card.get("target_type") == "AnyEnemy" and state["enemies"]:
                args["target_index"] = state["enemies"][0]["index"]
            state = game.act("play_card", **args)
        if state.get("decision") == "combat_play":
            state = game.act("end_turn")
            assert state.get("type") != "error"

    def test_many_cards_per_turn(self, game):
        """Play all playable cards in a single turn without errors."""
        state = game.start(seed="inf1")
        game.skip_neow(state)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        plays = 0
        for _ in range(20):
            if state.get("decision") != "combat_play":
                break
            playable = [c for c in state["hand"] if c.get("can_play")
                        and c["cost"] <= state["energy"] and c["type"] not in ("Status", "Curse")]
            if not playable:
                break
            card = playable[0]
            args = {"card_index": card["index"]}
            if card.get("target_type") == "AnyEnemy" and state["enemies"]:
                args["target_index"] = state["enemies"][0]["index"]
            state = game.act("play_card", **args)
            plays += 1
            assert state.get("type") != "error", f"Error after {plays} plays: {state.get('message')}"
        assert plays >= 2

    def test_infinite_card_loop(self, game):
        """Pommel Strike + Bloodletting infinite loop doesn't crash.

        Pommel Strike (1e): damage + draw 1
        Bloodletting (0e): lose HP + gain 2 energy
        Each cycle: net +1 energy, draws next card. Truly infinite.
        """
        state = game.start(seed="inf2")
        game.skip_neow(state)
        game.set_player(hp=80, max_hp=80, deck=["POMMEL_STRIKE"] * 5 + ["BLOODLETTING"] * 5)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")

        plays = 0
        for _ in range(60):
            if state.get("decision") != "combat_play":
                break
            hand = state.get("hand", [])
            energy = state.get("energy", 0)
            playable = [c for c in hand if c.get("can_play") and c["cost"] <= energy
                        and c["type"] not in ("Status", "Curse")]
            if not playable:
                break
            card = playable[0]
            args = {"card_index": card["index"]}
            if card.get("target_type") == "AnyEnemy" and state["enemies"]:
                args["target_index"] = state["enemies"][0]["index"]
            state = game.act("play_card", **args)
            plays += 1
            assert state.get("type") != "error", f"Error after {plays} plays: {state.get('message')}"

        # With Pommel Strike + Bloodletting, should play many cards before enemy dies
        assert plays >= 5, f"Expected infinite loop plays >= 5, got {plays}"

    def test_low_hp_death(self, game):
        """Player with 1 HP should die to any attack."""
        state = game.start(seed="ce2")
        game.skip_neow(state)
        game.set_player(hp=1)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        # Just end turn, beetle will kill us
        state = game.act("end_turn")
        # Might need another turn
        for _ in range(10):
            if state.get("decision") == "game_over":
                break
            if state.get("decision") == "combat_play":
                state = game.act("end_turn")
            else:
                break
        assert state["decision"] == "game_over"
        assert state["victory"] is False

    def test_reward_probe_nibbit_combat_does_not_repeat_identical_end_turn_state(self, game):
        state = _advance_to_nibbit(game)

        enemy_names = {enemy.get("name") for enemy in state.get("enemies", [])}
        assert "Nibbit" in enemy_names

        final_state = _play_without_repeating_identical_combat_state(game, state, max_steps=120)
        assert final_state.get("type") != "error"

    def test_console_fight_progresses_without_repeating_identical_state(self, game):
        game.start(seed="ce_console_progress")

        result = game.console("fight SHRINKER_BEETLE_WEAK")

        assert result["type"] == "console_result"
        state = result["state"]
        assert state["decision"] == "combat_play"

        final_state = _play_without_repeating_identical_combat_state(game, state, max_steps=80)
        assert final_state.get("type") != "error"

    def test_console_elite_fight_does_not_error_after_end_turn(self, game):
        game.start(seed="ce_elite_progress")

        result = game.console("fight BYGONE_EFFIGY_ELITE")

        assert result["type"] == "console_result"
        state = result["state"]
        assert state["decision"] == "combat_play"

        final_state = _play_without_repeating_identical_combat_state(game, state, max_steps=120)
        assert final_state.get("type") != "error"

    def test_event_probe_ceremonial_beast_does_not_error_after_end_turn(self, game):
        state = _advance_to_enemy(
            game,
            character="Defect",
            seed="event_probe_1",
            enemy_name="Ceremonial Beast",
            max_steps=300,
        )

        final_state = _play_without_repeating_identical_combat_state(game, state, max_steps=200)
        assert final_state.get("type") != "error"

    def test_console_phrog_parasite_elite_spawn_phase_does_not_stall(self, game):
        game.start(seed="ce_phrog_progress")

        result = game.console("fight PHROG_PARASITE_ELITE")

        assert result["type"] == "console_result"
        state = result["state"]
        assert state["decision"] == "combat_play"

        final_state = _play_without_repeating_identical_combat_state(game, state, max_steps=180)
        assert final_state.get("type") != "error"
