"""The finalize stage must not be able to finish without writing.

A golden-set eval lost 2 of 15 builds to a builder that generated a complete,
validated agent and then called ``finish`` without ever calling
``write_agent_files``. The prompt told it to do both; it did one.

The fix is structural rather than corrective: the finalize stage is given
``write_and_finish`` *instead of* ``finish``, and task-level tools replace the
config's entirely, so ending the stage without writing is no longer a thing the
model can express.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from gimle.hugin.apps.agent_builder.tools.write_and_finish import (
    write_and_finish,
)

BUILDER = Path("src/gimle/hugin/apps/agent_builder")

VALID = {
    "configs/demo.yaml": (
        "name: demo\ndescription: A demo\nsystem_template: demo_system\n"
        "tools:\n  - builtins.finish:finish\n"
    ),
    "tasks/main.yaml": "name: main\ndescription: d\nprompt: Do the thing.\n",
    "templates/demo_system.yaml": (
        "name: demo_system\ntemplate: You are a demo agent.\n"
    ),
}


def make_stack(files, output_path):
    """Return a stack stub carrying a payload and an output path."""
    environment = SimpleNamespace(
        env_vars={
            "generated_files": dict(files),
            "user_input": {
                "agent_name": "demo",
                "description": "d",
                "output_path": str(output_path),
            },
        },
        load_agent_from_path=lambda path: None,
    )
    return SimpleNamespace(agent=SimpleNamespace(environment=environment))


class TestTheStageCannotFinishWithoutWriting:
    """The structural property, asserted on the config the framework reads."""

    def _finalize(self):
        """Load the finalize task definition."""
        return yaml.safe_load(
            (BUILDER / "tasks" / "finalize_agent.yaml").read_text()
        )

    def test_finalize_declares_its_own_tools(self):
        """Task tools replace config tools; that is what makes this work."""
        assert self._finalize().get("tools")

    def test_finish_is_not_among_them(self):
        """The whole point: no way to end the stage without writing."""
        tools = self._finalize()["tools"]

        assert not any(
            tool == "finish" or tool.endswith(":finish") for tool in tools
        )

    def test_write_and_finish_is_among_them(self):
        """And there is a way to end it that writes."""
        assert "write_and_finish" in self._finalize()["tools"]

    def test_the_repair_tools_are_still_available(self):
        """A stage that cannot fix anything would just fail differently."""
        tools = set(self._finalize()["tools"])

        assert {"generate_tool", "validate_agent", "read_generated_file"} <= (
            tools
        )

    def test_it_keeps_every_other_tool_the_config_grants(self):
        """Defence in depth for the failure that scored 1/15 on a real eval.

        Stages share one stack, and task tools replace the config's entirely.
        Omitting a tool an earlier stage called used to change how that
        finished turn rendered -- a ``respond_with_text`` tool such as
        ``finish`` turned into a ``tool_use`` nothing answered, and the
        provider rejected the whole request. That root cause is fixed in the
        framework (``OracleResponse._tool_as_of_this_turn`` resolves the tool
        as of the turn that called it), so this list is no longer load-bearing
        for correctness. It is kept because a stage that cannot call what the
        build stage could is still a silent capability cut.
        """
        config = yaml.safe_load(
            (BUILDER / "configs" / "agent_builder.yaml").read_text()
        )
        expected = {
            tool
            for tool in config["tools"]
            if not tool.endswith("finish:finish")
            and tool not in OTHER_MODE_TOOLS
        }

        assert expected <= set(self._finalize()["tools"])


# Tools belonging to a mode other than building, which must NOT reach a build
# stage. `load_agent_files` replaces the whole payload with an agent read off
# disk, so a build stage calling it would discard the agent it just built.
# `analyze_traces` and `propose_change` diagnose an agent from run history a
# freshly built agent does not have.
OTHER_MODE_TOOLS = {"load_agent_files", "analyze_traces", "propose_change"}


class TestWriteAndFinish:
    """Writing and finishing are one step, and failure is not success."""

    def test_a_valid_payload_is_written_and_the_task_ends(self, tmp_path):
        """The normal path."""
        output = tmp_path / "demo"
        result = write_and_finish(make_stack(VALID, output), result="built it")

        assert not result.is_error
        assert result.response_interaction == "TaskResult"
        assert result.content["finish_type"] == "success"
        assert (output / "configs" / "demo.yaml").exists()

    def test_an_invalid_payload_ends_the_task_as_a_failure(self, tmp_path):
        """Finishing successfully over a refused write would be the old bug."""
        broken = dict(VALID)
        broken["configs/demo.yaml"] = (
            "name: demo\ndescription: d\nsystem_template: no_such_template\n"
        )
        output = tmp_path / "demo"

        result = write_and_finish(make_stack(broken, output), result="done")

        assert result.is_error
        assert result.content["finish_type"] == "failure"
        assert result.content["errors"]
        assert not output.exists()

    def test_the_output_path_defaults_to_the_run(self, tmp_path):
        """The model should not have to remember where the build was going."""
        output = tmp_path / "demo"

        write_and_finish(make_stack(VALID, output), result="built")

        assert (output / "tasks" / "main.yaml").exists()

    def test_an_explicit_output_path_wins(self, tmp_path):
        """Still overridable when a caller genuinely means somewhere else."""
        elsewhere = tmp_path / "elsewhere"

        write_and_finish(
            make_stack(VALID, tmp_path / "demo"),
            result="built",
            output_path=str(elsewhere),
        )

        assert (elsewhere / "tasks" / "main.yaml").exists()

    def test_no_known_output_path_is_an_error(self):
        """Better than writing somewhere arbitrary."""
        environment = SimpleNamespace(
            env_vars={"generated_files": dict(VALID), "user_input": {}},
            load_agent_from_path=lambda path: None,
        )
        stack = SimpleNamespace(agent=SimpleNamespace(environment=environment))

        result = write_and_finish(stack, result="built")

        assert result.is_error
        assert result.response_interaction != "TaskResult"


@pytest.mark.parametrize("stage", ["build_agent", "test_agent"])
def test_other_stages_keep_their_own_tools(stage):
    """Only finalize is constrained; the others still end normally.

    Writing during the build stage is exactly what was removed earlier -- it
    put an unreviewed agent on disk -- so this must not spread.
    """
    document = yaml.safe_load((BUILDER / "tasks" / f"{stage}.yaml").read_text())

    assert "write_and_finish" not in (document.get("tools") or [])
