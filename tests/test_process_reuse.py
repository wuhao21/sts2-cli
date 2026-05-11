"""Regression tests for reusing one headless process across runs."""


def test_start_run_can_be_called_twice_in_one_process(game):
    first = game.start(seed="reuse-first")
    assert first["type"] == "decision"
    assert first["decision"] == "event_choice"

    second = game.start(seed="reuse-second")

    assert second["type"] == "decision"
    assert second["decision"] == "event_choice"
    assert second["context"]["floor"] == 1
    assert second["player"]["hp"] == second["player"]["max_hp"]
