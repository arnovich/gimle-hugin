"""Tests for the remaining Phase 1 work on the agent builder.

Three separate concerns, each with a failure mode that is invisible without a
test: process-global state that leaks between agents, a repair loop that reads
back stale code, and generated artefacts that nothing else would notice were
missing.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from gimle.hugin.agent.environment import invalidate_modules_under
from gimle.hugin.apps.agent_builder.tools.agent_paths import materialise
from gimle.hugin.apps.agent_builder.tools.generate_tool import (
    PYTHON_TYPES,
    generate_tool,
)
from gimle.hugin.apps.agent_builder.tools.read_generated_file import (
    read_generated_file,
)
from gimle.hugin.utils.registry import Registry


def make_stack(files=None, user_input=None):
    """Return a stack stub carrying a generated payload."""
    environment = SimpleNamespace(
        env_vars={
            "generated_files": dict(files or {}),
            "user_input": user_input or {},
        },
        load_agent_from_path=lambda path: "demo",
    )
    return SimpleNamespace(agent=SimpleNamespace(environment=environment))


class TestRegistryCollisions:
    """Tool.registry is a process-global shared by every loaded agent."""

    def test_replacing_is_still_allowed_by_default(self):
        """Reloading an environment must keep working."""
        registry = Registry()
        first = SimpleNamespace(name="thing")
        second = SimpleNamespace(name="thing")

        registry.register(first)
        registry.register(second)

        assert registry.get("thing") is second

    def test_replace_false_refuses_to_shadow(self):
        """Callers loading generated code opt into strictness."""
        registry = Registry()
        registry.register(SimpleNamespace(name="finish"))

        with pytest.raises(ValueError):
            registry.register(SimpleNamespace(name="finish"), replace=False)

    def test_registering_the_same_instance_is_not_a_collision(self):
        """Idempotent registration must not look like shadowing."""
        registry = Registry()
        instance = SimpleNamespace(name="thing")
        registry.register(instance)

        registry.register(instance, replace=False)

        assert registry.get("thing") is instance


class TestModuleInvalidation:
    """import_module has no reload, so a repair loop re-ran the old code."""

    def test_modules_under_the_path_are_dropped(self, tmp_path, monkeypatch):
        """The whole point: the next import reads the file again."""
        import sys

        agent = tmp_path / "agent"
        tools = agent / "tools"
        tools.mkdir(parents=True)
        module = tools / "spy_tool_for_invalidation.py"
        module.write_text("VALUE = 1\n")
        monkeypatch.syspath_prepend(str(tools))

        import spy_tool_for_invalidation as first

        assert first.VALUE == 1

        module.write_text("VALUE = 2\n")
        assert invalidate_modules_under(str(agent))
        assert "spy_tool_for_invalidation" not in sys.modules

        import spy_tool_for_invalidation as second

        assert second.VALUE == 2

    def test_unrelated_modules_survive(self, tmp_path):
        """Invalidation is scoped to the agent, not the process."""
        import sys

        invalidate_modules_under(str(tmp_path / "nothing-here"))

        assert "json" in sys.modules

    def test_returns_empty_for_an_unknown_path(self, tmp_path):
        """Nothing cached under the path means nothing to drop."""
        assert invalidate_modules_under(str(tmp_path)) == []


class TestWriterDoesNotTouchTheGlobalRegistry:
    """Writing files should not load them into the running process."""

    def test_write_does_not_register_the_agent(self, tmp_path):
        """A generated tool must not shadow a builtin process-wide."""
        from gimle.hugin.apps.agent_builder.tools.write_agent_files import (
            write_agent_files,
        )

        files = {
            "configs/demo.yaml": (
                "name: demo\ndescription: d\nsystem_template: demo_system\n"
                "tools:\n  - builtins.finish:finish\n"
            ),
            "tasks/main.yaml": (
                "name: main\ndescription: d\nprompt: Do the thing.\n"
            ),
            "templates/demo_system.yaml": (
                "name: demo_system\ntemplate: You are demo.\n"
            ),
        }
        stack = make_stack(files, {"agent_name": "demo", "description": "d"})

        result = write_agent_files(stack, str(tmp_path / "demo"), "demo")

        assert not result.is_error, result.content
        assert result.content["registered_config"] is None


class TestReadGeneratedFile:
    """Repair needs to read one file, not re-invent it from an error."""

    @pytest.fixture
    def stack(self):
        """Return a payload with one tool in it."""
        return make_stack({"tools/fetch.py": "def fetch():\n    return 1\n"})

    def test_returns_the_content(self, stack):
        """The whole reason the tool exists."""
        result = read_generated_file(stack, "tools/fetch.py")

        assert not result.is_error
        assert "def fetch" in result.content["content"]

    def test_unknown_path_lists_what_exists(self, stack):
        """A wrong guess should not be a dead end."""
        result = read_generated_file(stack, "tools/nope.py")

        assert result.is_error
        assert "tools/fetch.py" in result.content["available"]

    def test_traversal_is_refused(self, stack):
        """The key rules apply here as everywhere else."""
        assert read_generated_file(stack, "../../etc/passwd").is_error

    def test_nothing_generated_is_an_error(self):
        """Distinguishes 'no payload' from 'no such file'."""
        assert read_generated_file(make_stack(), "tools/fetch.py").is_error

    def test_large_files_are_truncated(self, stack):
        """A repair loop can read several; context is finite."""
        stack.agent.environment.env_vars["generated_files"]["tools/big.py"] = (
            "# pad\n" * 20_000
        )

        result = read_generated_file(stack, "tools/big.py")

        assert result.content["truncated"] is True
        assert len(result.content["content"]) <= 20_000


class TestGeneratedToolQuality:
    """What the generator emits is what the user has to maintain."""

    @pytest.mark.parametrize(
        "declared,expected",
        [
            ("integer", "int"),
            ("number", "float"),
            ("boolean", "bool"),
            ("string", "str"),
        ],
    )
    def test_declared_types_become_real_hints(self, declared, expected):
        """Everything used to be typed str regardless of the schema."""
        stack = make_stack()
        generate_tool(
            tool_name="fetch",
            description="d",
            parameters_schema={
                "value": {
                    "type": declared,
                    "description": "v",
                    "required": True,
                }
            },
            implementation_code=(
                "return ToolResponse(is_error=False, content={})"
            ),
            agent_name="a",
            stack=stack,
        )
        code = stack.agent.environment.env_vars["generated_files"][
            "tools/fetch.py"
        ]

        assert f"value: {expected}" in code

    def test_every_schema_type_is_mapped(self):
        """An unmapped type would silently fall back to str."""
        assert set(PYTHON_TYPES) >= {
            "string",
            "integer",
            "number",
            "boolean",
            "array",
            "object",
        }

    def test_failures_carry_a_traceback(self):
        """str(e) alone told the repair loop nothing about where it broke."""
        stack = make_stack()
        generate_tool(
            tool_name="fetch",
            description="d",
            parameters_schema={},
            implementation_code=(
                "return ToolResponse(is_error=False, content={})"
            ),
            agent_name="a",
            stack=stack,
        )
        code = stack.agent.environment.env_vars["generated_files"][
            "tools/fetch.py"
        ]

        assert "traceback" in code
        assert "_redact" in code

    def test_stub_mode_emits_a_signature_that_raises(self):
        """--stub-tools finally gives the long-dead flag a meaning."""
        stack = make_stack(
            user_input={"full_implementation": False},
        )
        generate_tool(
            tool_name="fetch",
            description="d",
            parameters_schema={},
            implementation_code="import yfinance",
            agent_name="a",
            stack=stack,
        )
        code = stack.agent.environment.env_vars["generated_files"][
            "tools/fetch.py"
        ]

        assert "NotImplementedError" in code
        assert "yfinance" not in code
        compile(code, "<generated>", "exec")


class TestGeneratedArtefacts:
    """The directory should explain itself without hugin monitor."""

    def _files(self):
        """Return a small generated payload."""
        return {
            "configs/demo.yaml": "name: demo\n",
            "tasks/main.yaml": "name: main\n",
            "tools/fetch.yaml": "name: fetch\n",
            "tools/fetch.py": "import pandas\n",
        }

    def test_build_report_names_the_tools(self):
        """Understanding the agent used to require opening the trace."""
        files = materialise(
            self._files(), "demo", "Fetch things", "/tmp/demo", "main"
        )

        assert "fetch" in files["BUILD_REPORT.md"]
        assert "Fetch things" in files["BUILD_REPORT.md"]

    def test_build_report_carries_the_run_command(self):
        """The one command that actually works, next to the agent."""
        files = materialise(self._files(), "demo", "d", "/tmp/demo", "main")

        assert "uv run hugin run --task main" in files["BUILD_REPORT.md"]

    def test_requirements_lists_observed_imports(self):
        """Missing dependencies were previously the user's problem to find."""
        files = materialise(
            self._files(),
            "demo",
            "d",
            "/tmp/demo",
            "main",
            observed_imports=["pandas"],
        )

        assert "pandas" in files["requirements.txt"]

    def test_requirements_says_it_is_unverified(self):
        """The names come from an LLM and may not exist on any index."""
        files = materialise(
            self._files(),
            "demo",
            "d",
            "/tmp/demo",
            "main",
            observed_imports=["pandas"],
        )

        assert "not verified" in files["requirements.txt"]

    def test_no_requirements_file_without_dependencies(self):
        """An empty requirements.txt is noise."""
        files = materialise(self._files(), "demo", "d", "/tmp/demo", "main")

        assert "requirements.txt" not in files


class TestNonInteractiveWizard:
    """`hugin create` had to be driven by hand, so it was never tested."""

    def _args(self, **overrides):
        """Return a parsed-args stub with the new flags."""
        import argparse

        values = {
            "name": None,
            "description": None,
            "model": None,
            "builder_model": None,
            "output": None,
            "stub_tools": False,
            "yes": False,
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    def test_flags_replace_every_prompt(self, tmp_path):
        """No stdin is touched, which is what makes it scriptable."""
        from gimle.hugin.cli.create_agent import run_wizard

        result = run_wizard(
            args=self._args(
                name="My Agent",
                description="Do a thing",
                output=str(tmp_path / "out"),
                yes=True,
            )
        )

        assert result["agent_name"] == "my_agent"
        assert result["description"] == "Do a thing"

    def test_stub_tools_flag_reaches_the_build(self, tmp_path):
        """Otherwise the flag is decorative, as full_implementation was."""
        from gimle.hugin.cli.create_agent import run_wizard

        result = run_wizard(
            args=self._args(
                name="a",
                description="d",
                output=str(tmp_path / "out"),
                yes=True,
                stub_tools=True,
            )
        )

        assert result["full_implementation"] is False

    def test_yes_without_a_description_exits(self, tmp_path):
        """Failing fast beats prompting a script that cannot answer."""
        from gimle.hugin.cli.create_agent import run_wizard

        with pytest.raises(SystemExit):
            run_wizard(args=self._args(name="a", yes=True))

    def test_unsafe_output_path_exits(self):
        """The guard applies before the build, not after it."""
        from gimle.hugin.cli.create_agent import run_wizard

        with pytest.raises(SystemExit):
            run_wizard(
                args=self._args(
                    name="a",
                    description="d",
                    output=str(Path.home()),
                    yes=True,
                )
            )


class TestModelsComeFromTheRegistry:
    """The wizard restated a model list that went stale on every addition."""

    def test_anthropic_models_are_discovered(self):
        """Not the hardcoded three."""
        from gimle.hugin.cli.create_agent import _registry_models

        assert "sonnet-latest" in _registry_models("anthropic")

    def test_unknown_provider_is_empty(self):
        """A typo must not raise inside the wizard."""
        from gimle.hugin.cli.create_agent import _registry_models

        assert _registry_models("nope") == []
