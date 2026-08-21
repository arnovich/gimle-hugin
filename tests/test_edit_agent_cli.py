"""`hugin create --edit` -- the wiring, and the refusals that come before it.

A build that is going to be refused should be refused before it runs, not
after: a multi-stage LLM build has already been paid for by the time the
writer looks at the path. The build wizard learned that with
``check_output_path``; the edit wizard applies the same rule to the directory
it is asked to edit.
"""

import argparse

import pytest
import yaml

from gimle.hugin.apps import get_apps_path
from gimle.hugin.cli.create_agent import run_edit_wizard

BUILDER = get_apps_path() / "agent_builder"


def _args(**overrides):
    values = {
        "edit": None,
        "instruction": None,
        "yes": True,
        "dry_run": False,
        "builder_model": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


@pytest.fixture
def agent_dir(tmp_path):
    """A directory that looks like an agent."""
    root = tmp_path / "demo_agent"
    (root / "configs").mkdir(parents=True)
    (root / "configs" / "demo.yaml").write_text("name: demo\n")
    return root


class TestTheEditWizard:
    """What it collects, and what it hands to the builder."""

    def test_it_collects_the_path_and_instruction(self, agent_dir):
        """No stdin touched, so an edit is scriptable like a build."""
        result = run_edit_wizard(
            _args(edit=str(agent_dir), instruction="add a retry")
        )

        assert result["agent_path"] == str(agent_dir.resolve())
        assert result["instruction"] == "add a retry"
        assert result["edit"] is True

    def test_it_writes_back_where_it_read_from(self, agent_dir):
        """An edit that wrote elsewhere would fork the agent, not change it."""
        result = run_edit_wizard(
            _args(edit=str(agent_dir), instruction="add a retry")
        )

        assert result["output_path"] == result["agent_path"]


class TestRefusalsHappenFirst:
    """Each of these used to cost a full build before being noticed."""

    def test_a_missing_directory_exits(self, tmp_path):
        """The path is typed by a human and is routinely wrong."""
        with pytest.raises(SystemExit) as exit_info:
            run_edit_wizard(_args(edit=str(tmp_path / "nope"), instruction="x"))

        assert exit_info.value.code == 2

    def test_a_directory_that_is_not_an_agent_exits(self, tmp_path):
        """Pointing at a source tree should not start a build."""
        (tmp_path / "src").mkdir()

        with pytest.raises(SystemExit) as exit_info:
            run_edit_wizard(_args(edit=str(tmp_path / "src"), instruction="x"))

        assert exit_info.value.code == 2

    def test_unattended_without_an_instruction_exits(self, agent_dir):
        """--yes cannot prompt, so it must say what is missing."""
        with pytest.raises(SystemExit) as exit_info:
            run_edit_wizard(_args(edit=str(agent_dir), yes=True))

        assert exit_info.value.code == 2


class TestTheEditTask:
    """The task the CLI selects, checked as data rather than by running it."""

    def _task(self, name):
        return yaml.safe_load((BUILDER / "tasks" / f"{name}.yaml").read_text())

    def test_it_cannot_finish_without_writing(self):
        """Same guarantee the finalize stage relies on: no bare `finish`."""
        tools = self._task("edit_agent")["tools"]

        assert not any(tool.endswith("finish:finish") for tool in tools)
        assert "write_and_finish" in tools

    def test_it_can_load_and_read_before_regenerating(self):
        """Regenerating an unread file is the data-loss path this avoids."""
        tools = self._task("edit_agent")["tools"]

        assert "load_agent_files" in tools
        assert "read_generated_file" in tools

    @pytest.mark.parametrize(
        "task_name", ["build_agent", "review_agent", "finalize_agent"]
    )
    @pytest.mark.parametrize(
        "tool", ["load_agent_files", "analyze_traces", "propose_change"]
    )
    def test_no_build_stage_gets_another_mode_s_tools(self, task_name, tool):
        """`load_agent_files` replaces the payload wholesale.

        A build stage calling it would discard the agent that build just
        produced. The improve-mode tools are pointless mid-build for the
        mirror-image reason: a freshly built agent has no run history.
        """
        task = self._task(task_name)

        assert tool not in (task.get("tools") or [])
