"""The agent builder must be able to study existing examples.

``list_examples`` and ``read_example`` shipped but were absent from
``configs/agent_builder.yaml``, so ~495 lines of example-catalog tooling was
unreachable and the builder invented agent structure from the prompt alone.
These tests pin the wiring and the context caps that keep it affordable.
"""

from pathlib import Path

import yaml

BUILDER = Path(__file__).resolve().parents[1] / (
    "src/gimle/hugin/apps/agent_builder"
)


def _config():
    """Load the agent_builder config as plain YAML."""
    with open(BUILDER / "configs" / "agent_builder.yaml") as handle:
        return yaml.safe_load(handle)


def _tool_yaml(name):
    """Load a builder tool definition as plain YAML."""
    with open(BUILDER / "tools" / f"{name}.yaml") as handle:
        return yaml.safe_load(handle)


class TestExampleToolsAreWired:
    """The config is what decides whether a tool exists for the agent."""

    def test_list_examples_in_config(self):
        """Without this line the catalogue is dead code."""
        assert "list_examples" in _config()["tools"]

    def test_read_example_in_config(self):
        """Listing examples is useless if none can be read."""
        assert "read_example" in _config()["tools"]

    def test_every_configured_tool_has_a_definition(self):
        """A config naming a tool with no YAML fails at load, not at use."""
        for tool in _config()["tools"]:
            if tool.startswith("builtins."):
                continue
            assert (BUILDER / "tools" / f"{tool}.yaml").exists(), tool
            assert (BUILDER / "tools" / f"{tool}.py").exists(), tool


class TestContextCaps:
    """The builder's stages share one stack that is never truncated."""

    def test_read_example_is_capped(self):
        """A single example can be tens of KB; it must not accumulate."""
        options = _tool_yaml("read_example")["options"]
        assert options["include_only_in_context_window"] is True
        assert options["context_window"] <= 2

    def test_list_examples_is_capped(self):
        """The index is a catalogue, useful once."""
        options = _tool_yaml("list_examples")["options"]
        assert options["include_only_in_context_window"] is True
        assert options["context_window"] <= 2


class TestPromptsDirectTheBuilderToStudyFirst:
    """A capability the prompts never mention will not get used."""

    def test_task_prompt_names_both_tools(self):
        """The concrete recipe overrides the system prompt, so it must say so."""
        with open(BUILDER / "tasks" / "build_agent.yaml") as handle:
            prompt = yaml.safe_load(handle)["prompt"]
        assert "list_examples" in prompt
        assert "read_example" in prompt

    def test_study_step_precedes_generation(self):
        """Studying after generating would be pointless."""
        with open(BUILDER / "tasks" / "build_agent.yaml") as handle:
            prompt = yaml.safe_load(handle)["prompt"]
        assert prompt.index("list_examples") < prompt.index("generate_config")

    def test_system_template_names_both_tools(self):
        """Belt and braces: the workflow list mentions them too."""
        with open(BUILDER / "templates" / "builder_system.yaml") as handle:
            template = yaml.safe_load(handle)["template"]
        assert "list_examples" in template
        assert "read_example" in template


class TestToolsActuallyWork:
    """Wiring a broken tool in would be worse than leaving it out."""

    def test_list_examples_returns_real_examples(self):
        """Reads the repo's examples/ tree rather than a hardcoded list."""
        from gimle.hugin.apps.agent_builder.tools.list_examples import (
            list_examples,
        )

        result = list_examples()

        assert not result.is_error
        assert result.content["examples"]

    def test_read_example_returns_a_known_example(self):
        """basic_agent is the canonical starting point and must be readable."""
        from gimle.hugin.apps.agent_builder.tools.read_example import (
            read_example,
        )

        result = read_example(example_name="basic_agent")

        assert not result.is_error

    def test_read_example_reports_unknown_example(self):
        """A hallucinated example name must not look like success."""
        from gimle.hugin.apps.agent_builder.tools.read_example import (
            read_example,
        )

        result = read_example(example_name="no_such_example_xyz")

        assert result.is_error

    def test_neither_tool_declares_stack(self):
        """Both are injected-arg-free; declaring stack would change the call."""
        import inspect

        from gimle.hugin.apps.agent_builder.tools.list_examples import (
            list_examples,
        )
        from gimle.hugin.apps.agent_builder.tools.read_example import (
            read_example,
        )

        assert "stack" not in inspect.signature(list_examples).parameters
        assert "stack" not in inspect.signature(read_example).parameters
