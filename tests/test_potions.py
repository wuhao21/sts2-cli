"""Tests for potion behavior."""


class TestPotions:
    def test_anyplayer_potion_targets_player(self, game):
        state = game.start(seed="p3")
        phial_holster = next(
            (
                option
                for option in state["options"]
                if option.get("text_key") == "NEOW.pages.INITIAL.options.PHIAL_HOLSTER"
                and not option.get("is_locked")
            ),
            None,
        )
        assert phial_holster is not None

        state = game.act("choose_option", option_index=phial_holster["index"])
        state = game.skip_neow(state)

        potions = state["player"]["potions"]
        liquid_bronze = next(potion for potion in potions if potion["id"] == "LIQUID_BRONZE")
        assert liquid_bronze["target_type"] == "AnyPlayer"

        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        state = game.act("use_potion", potion_index=liquid_bronze["index"])

        player_powers = state.get("player_powers") or []
        assert any(
            power["id"] == "THORNS_POWER" and power["amount"] >= 3
            for power in player_powers
        )
