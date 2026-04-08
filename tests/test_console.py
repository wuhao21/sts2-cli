"""Tests for the console bridge."""


class TestConsoleMetadata:
    def test_dump_console_commands_returns_expected_shape(self, game):
        result = game.send({"cmd": "dump_console_commands"})

        assert result["type"] == "console_commands"
        assert "count" in result
        assert "commands" in result
        assert result["count"] == len(result["commands"])

    def test_dump_console_commands_contains_known_commands(self, game):
        result = game.send({"cmd": "dump_console_commands"})

        cmd_names = {cmd["cmd_name"] for cmd in result["commands"] if cmd.get("cmd_name")}

        assert {"gold", "fight", "act"}.issubset(cmd_names)

    def test_dump_console_command_entries_have_expected_fields(self, game):
        result = game.send({"cmd": "dump_console_commands"})

        for entry in result["commands"]:
            assert "class_name" in entry
            assert "type_name" in entry
            assert "cmd_name" in entry or "instantiate_error" in entry

            if "instantiate_error" not in entry:
                assert "debug_only" in entry
                assert "is_networked" in entry
                assert "args" in entry
                assert "description" in entry


class TestConsoleExecution:
    def test_console_requires_input(self, game):
        game.start(seed="console_req1")

        result = game.send({"cmd": "console"})

        assert result["type"] == "error"
        assert "Provide 'input'" in result["message"]

    def test_console_gold_updates_player_state(self, game):
        game.start(seed="console_gold1")

        result = game.console("gold 123")

        assert result["type"] == "console_result"
        assert result["state"]["player"]["gold"] == 222

    def test_console_fight_transitions_to_combat_play(self, game):
        game.start(seed="console_fight1")

        result = game.console("fight SHRINKER_BEETLE_WEAK")

        assert result["type"] == "console_result"
        assert result["state"]["decision"] == "combat_play"
        assert "hand" in result["state"]
        assert "enemies" in result["state"]

    def test_console_result_keeps_state_payload(self, game):
        game.start(seed="console_state1")

        result = game.console("gold 1")

        assert result["type"] == "console_result"
        assert "state" in result
        assert isinstance(result["state"], dict)
        assert "player" in result["state"]

    def test_console_dump_returns_captured_output(self, game):
        game.start(seed="console_dump1")

        result = game.console("dump")

        assert result["type"] == "console_result"
        assert "output" in result
        assert "EPOCHS" in result["output"]

    def test_console_async_failure_returns_error(self, game):
        game.start(seed="console_act1")

        result = game.console("act 2")

        assert result["type"] == "error"
        assert "NullReferenceException" in result["message"]
        assert "NextAct" in result["output"]

    def test_console_file_manager_commands_do_not_raise_missing_method(self, game):
        game.start(seed="console_open1")

        result = game.console("open saves")

        assert "MissingMethodException" not in result.get("message", "")
