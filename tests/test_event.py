"""Tests for events."""
import pytest


class TestNeowEvent:
    def test_neow_is_first_event(self, game):
        state = game.start(seed="ne1")
        assert state["decision"] == "event_choice"
        assert "Neow" in str(state.get("event_name", ""))

    def test_neow_options(self, game):
        state = game.start(seed="ne2")
        for opt in state["options"]:
            assert "title" in opt
            assert isinstance(opt["title"], str)
            assert "is_locked" in opt

    def test_neow_option_vars(self, game):
        state = game.start(seed="ne3")
        for opt in state["options"]:
            if opt.get("vars"):
                for k, v in opt["vars"].items():
                    assert isinstance(v, (int, float))

    def test_choose_neow(self, game):
        state = game.start(seed="ne4")
        opts = [o for o in state["options"] if not o.get("is_locked")]
        state = game.act("choose_option", option_index=opts[0]["index"])
        assert state.get("decision") is not None


class TestEventDescriptions:
    def test_no_ismultiplayer_tag(self, game):
        state = game.start(seed="ed1")
        for opt in state.get("options", []):
            d = opt.get("description") or ""
            assert "IsMultiplayer" not in d


class TestEventSelectionContinuation:
    @pytest.mark.parametrize("option_index, replacement", [
        (0, "CARD.PECK"),
        (2, "CARD.TORIC_TOUGHNESS"),
    ])
    def test_wood_carvings_finishes_after_transform(self, game, option_index, replacement):
        state = game.start(seed="jester-2nd")
        game.skip_neow(state)
        game.enter_room("event", event="WOOD_CARVINGS")

        state = game.act("choose_option", option_index=option_index)
        assert state["decision"] == "card_select"
        original = state["cards"][0]["id"]
        deck_before = [c["id"] for c in state["player"]["deck"]]

        state = game.act("select_cards", indices="0")

        assert state["decision"] == "map_select"
        deck_after = [c["id"] for c in state["player"]["deck"]]
        assert len(deck_after) == len(deck_before)
        assert deck_after.count(replacement) == deck_before.count(replacement) + 1
        assert deck_after.count(original) == deck_before.count(original) - 1

    def test_luminous_choir_finishes_after_removal_and_curse(self, game):
        state = game.start(seed="jester-2nd")
        game.skip_neow(state)
        game.enter_room("event", event="LUMINOUS_CHOIR")

        state = game.act("choose_option", option_index=0)
        assert state["decision"] == "card_select"
        removed = [c["id"] for c in state["cards"][:2]]
        deck_before = [c["id"] for c in state["player"]["deck"]]

        state = game.act("select_cards", indices="0,1")

        assert state["decision"] == "map_select"
        expected = deck_before.copy()
        for card_id in removed:
            expected.remove(card_id)
        expected.append("CARD.SPORE_MIND")
        assert sorted(c["id"] for c in state["player"]["deck"]) == sorted(expected)

    def test_slippery_bridge_keeps_legitimate_follow_up_choices(self, game):
        state = game.start(seed="bridge-continuation")
        game.skip_neow(state)
        state = game.enter_room("event", event="SLIPPERY_BRIDGE")
        hp_before = state["player"]["hp"]
        deck_before = state["player"]["deck_size"]

        for hp_loss in (3, 4):
            state = game.act("choose_option", option_index=1)
            hp_before -= hp_loss
            assert state["decision"] == "event_choice"
            assert len(state["options"]) == 2
            assert state["player"]["hp"] == hp_before
            assert state["player"]["deck_size"] == deck_before

        state = game.act("choose_option", option_index=0)
        assert state["decision"] == "map_select"
        assert state["player"]["deck_size"] == deck_before - 1

    @pytest.mark.parametrize("action, cards_added", [
        ("select_card_reward", 2),
        ("skip_card_reward", 0),
    ])
    def test_event_waits_through_consecutive_card_rewards(self, game, action, cards_added):
        state = game.start(seed="jester-2nd")
        deck_before = state["player"]["deck_size"]
        option = next(o for o in state["options"] if o["text_key"].endswith(".KALEIDOSCOPE"))
        state = game.act("choose_option", option_index=option["index"])

        for _ in range(2):
            assert state["decision"] == "card_reward"
            if action == "select_card_reward":
                state = game.act(action, card_index=0)
            else:
                state = game.act(action)

        assert state["decision"] == "map_select"
        assert state["player"]["deck_size"] == deck_before + cards_added

    def test_event_finishes_after_bundle_selection(self, game):
        state = game.start(seed="run_5")
        deck_before = state["player"]["deck_size"]
        option = next(o for o in state["options"] if o["text_key"].endswith(".SCROLL_BOXES"))
        state = game.act("choose_option", option_index=option["index"])
        assert state["decision"] == "bundle_select"
        chosen_names = [c["name"] for c in state["bundles"][0]["cards"]]
        deck_before_names = [c["name"] for c in state["player"]["deck"]]

        state = game.act("select_bundle", bundle_index=0)

        assert state["decision"] == "map_select"
        assert state["player"]["deck_size"] == deck_before + len(chosen_names)
        assert sorted(c["name"] for c in state["player"]["deck"]) == sorted(deck_before_names + chosen_names)

    def test_second_event_choice_preserves_pending_selection(self, game):
        state = game.start(seed="jester-2nd")
        game.skip_neow(state)
        game.enter_room("event", event="WOOD_CARVINGS")
        state = game.act("choose_option", option_index=0)
        assert state["decision"] == "card_select"
        cards_before = state["cards"]

        state = game.act("choose_option", option_index=2)
        assert state["decision"] == "card_select"
        assert state["cards"] == cards_before

        state = game.act("select_cards", indices="0")
        assert state["decision"] == "map_select"
        ids = [c["id"] for c in state["player"]["deck"]]
        assert ids.count("CARD.PECK") == 1
        assert "CARD.TORIC_TOUGHNESS" not in ids
