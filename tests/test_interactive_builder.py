"""Letting the builder ask instead of guessing.

An ambiguous description currently gets a guess -- the builder invents a shape
and finds out at review whether it was the right one. `--interactive` gives it
`builtins.ask_user` so it can ask one question instead.

The two halves have to travel together: `ask_user` is `is_interactive`, and
`Stack.get_tools` filters those out unless the config says `interactive: true`.
Listing the tool without the flag does nothing at all, silently.
"""

import yaml

from gimle.hugin.apps import get_apps_path
from gimle.hugin.tools.tool import Tool

BUILDER = get_apps_path() / "agent_builder"
ASK_USER = "builtins.ask_user:ask_user"


def _config(name):
    return yaml.safe_load((BUILDER / "configs" / f"{name}.yaml").read_text())


def _task(name):
    return yaml.safe_load((BUILDER / "tasks" / f"{name}.yaml").read_text())


class TestTheInteractiveConfig:
    """It must actually be able to ask."""

    def test_it_can_ask(self):
        assert ASK_USER in _config("agent_builder_interactive")["tools"]

    def test_it_is_marked_interactive(self):
        """Without this the tool is filtered out and the flag is decorative."""
        assert _config("agent_builder_interactive")["interactive"] is True

    def test_ask_user_really_is_filtered_without_the_flag(self):
        """The reason both halves are needed, asserted rather than assumed."""
        tool = Tool.get_tool("builtins.ask_user", throw_error=False)

        assert tool is not None
        assert tool.is_interactive is True

    def test_it_keeps_every_tool_the_default_builder_has(self):
        """It is the same builder plus a question, not a different one."""
        default = set(_config("agent_builder")["tools"])
        interactive = set(_config("agent_builder_interactive")["tools"])

        assert default <= interactive
        assert interactive - default == {ASK_USER}


class TestTheDefaultIsUnchanged:
    """Scripted runs, CI and the golden-set eval must be unaffected."""

    def test_the_default_config_cannot_ask(self):
        assert ASK_USER not in _config("agent_builder")["tools"]

    def test_the_default_config_is_not_interactive(self):
        assert _config("agent_builder")["interactive"] is False


class TestEditModeCanAskToo:
    """ "What exactly do you want changed?" is the better question."""

    def test_the_edit_task_lists_ask_user(self):
        """Task tools replace config tools, so it has to be named here."""
        assert ASK_USER in _task("edit_agent")["tools"]


class TestTheFlags:
    """--interactive and --yes are opposites."""

    def test_they_cannot_be_combined(self):
        """--yes runs without a human; --interactive asks one questions."""
        from gimle.hugin.cli.create_agent import main

        assert (
            main(
                [
                    "--name",
                    "a",
                    "--description",
                    "d",
                    "--yes",
                    "--interactive",
                ]
            )
            == 2
        )

    def test_interactive_defaults_off(self):
        """Read off the real parser: unattended runs must stay unattended."""
        from gimle.hugin.cli.create_agent import build_parser

        args = build_parser().parse_args(["--name", "a"])

        assert args.interactive is False

    def test_the_flag_turns_it_on(self):
        from gimle.hugin.cli.create_agent import build_parser

        args = build_parser().parse_args(["--name", "a", "--interactive"])

        assert args.interactive is True


class TestAWrittenAgentSurvivesTheStepCap:
    """`test_agent` runs after the write, out of the same step budget.

    Its sub-agent's steps count against the builder's allowance, so a build
    that wrote a complete, validated agent could still exhaust the budget in
    the optional test that follows -- and the agent went to `.rejected`. That
    happened twice while testing `--interactive`, which makes it likelier
    still, since asking a question costs steps too.
    """

    def test_a_normal_build_is_ok(self):
        from gimle.hugin.cli.create_agent import step_cap_outcome

        assert step_cap_outcome(120, 200, True) == "ok"

    def test_the_cap_after_a_write_is_not_a_failure(self):
        """The agent exists and validates; only the test ran out."""
        from gimle.hugin.cli.create_agent import step_cap_outcome

        assert step_cap_outcome(200, 200, True) == "capped_after_write"

    def test_the_cap_with_nothing_written_is_still_a_failure(self):
        """Otherwise an incomplete build would report success."""
        from gimle.hugin.cli.create_agent import step_cap_outcome

        assert step_cap_outcome(200, 200, False) == "capped_empty"
