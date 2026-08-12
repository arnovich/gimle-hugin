"""Tests for the agent builder's static validator.

Two obligations, and the second is the one that matters. The validator must
catch each class of breakage (one deliberately broken fixture per check), and
it must stay silent on the repo's own agents -- a validator that fails the
shipped examples is wrong about the framework, not right about the examples.
"""

from pathlib import Path

import pytest

from gimle.hugin.apps.agent_builder.tools.validate_agent import (
    collect_files,
    validate_files,
)

REPO = Path(__file__).resolve().parents[1]


def agent(**overrides):
    """Return a valid single-tool agent, with the given files replaced."""
    files = {
        "configs/demo.yaml": (
            "name: demo\n"
            "description: A demo\n"
            "system_template: demo_system\n"
            "tools:\n"
            "  - fetch_prices\n"
            "  - builtins.finish:finish\n"
        ),
        "tasks/main.yaml": (
            "name: main\n"
            "description: Main task\n"
            "parameters:\n"
            "  ticker:\n"
            "    type: string\n"
            "    description: Ticker\n"
            "    required: true\n"
            "prompt: 'Look up {{ ticker.value }} using fetch_prices.'\n"
        ),
        "templates/demo_system.yaml": (
            "name: demo_system\ntemplate: You are a demo agent.\n"
        ),
        "tools/fetch_prices.yaml": (
            "name: fetch_prices\n"
            "description: Fetch prices\n"
            "parameters:\n"
            "  ticker:\n"
            "    type: string\n"
            "    description: Ticker\n"
            "    required: true\n"
            "implementation_path: fetch_prices:fetch_prices\n"
        ),
        "tools/fetch_prices.py": (
            "def fetch_prices(ticker, stack=None):\n"
            "    return {'ticker': ticker}\n"
        ),
    }
    files.update(overrides)
    return {k: v for k, v in files.items() if v is not None}


def errors_of(report, check):
    """Return the error messages recorded under one check name."""
    return [e for e in report["errors"] if e["check"] == check]


def warnings_of(report, check):
    """Return the warnings recorded under one check name."""
    return [w for w in report["warnings"] if w["check"] == check]


class TestCleanAgentPasses:
    """A correct agent must produce no findings at all."""

    def test_valid_agent_is_ok(self):
        """The baseline fixture every other test mutates."""
        report = validate_files(agent())
        assert report["ok"], report["errors"]

    def test_valid_agent_has_no_warnings(self):
        """Warnings on a correct agent would train the model to ignore them."""
        assert validate_files(agent())["warnings"] == []


class TestStructure:
    """Missing pieces, and the shared-module convention."""

    def test_missing_config_is_an_error(self):
        """An agent with no config cannot be run."""
        report = validate_files(agent(**{"configs/demo.yaml": None}))
        assert errors_of(report, "structure")

    def test_missing_task_is_an_error(self):
        """An agent with no task has nothing to do."""
        report = validate_files(agent(**{"tasks/main.yaml": None}))
        assert errors_of(report, "structure")

    def test_implementation_path_naming_a_missing_module_is_an_error(self):
        """The most common way a tool silently fails to register."""
        report = validate_files(
            agent(
                **{
                    "tools/fetch_prices.yaml": (
                        "name: fetch_prices\n"
                        "description: Fetch\n"
                        "implementation_path: no_such_module:fetch_prices\n"
                    )
                }
            )
        )
        assert errors_of(report, "structure")

    def test_helper_module_without_a_definition_is_allowed(self):
        """Shared helper modules are a normal pattern, not a defect."""
        report = validate_files(
            agent(**{"tools/helpers.py": "VALUE = 1\n"})
        )
        assert report["ok"], report["errors"]

    def test_several_tools_may_share_one_module(self):
        """examples/parallel_agents does exactly this."""
        report = validate_files(
            agent(
                **{
                    "tools/extra.yaml": (
                        "name: extra\n"
                        "description: Extra\n"
                        "implementation_path: fetch_prices:extra\n"
                    ),
                    "tools/fetch_prices.py": (
                        "def fetch_prices(ticker, stack=None):\n"
                        "    return {}\n"
                        "\n\n"
                        "def extra(stack=None):\n"
                        "    return {}\n"
                    ),
                }
            )
        )
        assert report["ok"], report["errors"]


class TestReferenceResolution:
    """A name that resolves to nothing breaks only at runtime today."""

    def test_unknown_template_reference_is_an_error(self):
        """The typo case: system_template names no registered template."""
        report = validate_files(
            agent(
                **{
                    "configs/demo.yaml": (
                        "name: demo\n"
                        "description: A demo\n"
                        "system_template: demo_sytsem\n"
                    )
                }
            )
        )
        assert errors_of(report, "template-reference")

    def test_prose_system_prompt_is_not_a_reference(self):
        """An inline prompt must not be mistaken for a broken reference."""
        report = validate_files(
            agent(
                **{
                    "configs/demo.yaml": (
                        "name: demo\n"
                        "description: A demo\n"
                        "system_template: You are a helpful demo agent.\n"
                    )
                }
            )
        )
        assert not errors_of(report, "template-reference")

    def test_explicit_jinja_template_is_not_a_reference(self):
        """The documented '{{ name.template }}' form must pass."""
        report = validate_files(
            agent(
                **{
                    "configs/demo.yaml": (
                        "name: demo\n"
                        "description: A demo\n"
                        'system_template: "{{ demo_system.template }}"\n'
                    )
                }
            )
        )
        assert not errors_of(report, "template-reference")

    def test_undefined_tool_is_an_error(self):
        """A config naming a tool that does not exist."""
        report = validate_files(
            agent(
                **{
                    "configs/demo.yaml": (
                        "name: demo\n"
                        "description: A demo\n"
                        "system_template: demo_system\n"
                        "tools:\n"
                        "  - no_such_tool\n"
                    )
                }
            )
        )
        assert errors_of(report, "tool-reference")

    def test_unregistered_builtin_is_an_error(self):
        """A misspelled builtin resolves to nothing."""
        report = validate_files(
            agent(
                **{
                    "configs/demo.yaml": (
                        "name: demo\n"
                        "description: A demo\n"
                        "system_template: demo_system\n"
                        "tools:\n"
                        "  - builtins.finsh:finish\n"
                    )
                }
            )
        )
        assert errors_of(report, "tool-reference")

    def test_real_builtin_alias_resolves(self):
        """The 'builtins.x:alias' form is the normal spelling."""
        assert validate_files(agent())["ok"]


class TestReservedNames:
    """Registry.register overwrites silently on a process-global registry."""

    def test_tool_shadowing_a_builtin_is_an_error(self):
        """A generated 'finish' would replace the real one process-wide."""
        report = validate_files(
            agent(
                **{
                    "tools/fetch_prices.yaml": (
                        "name: builtins.finish\n"
                        "description: Nope\n"
                        "implementation_path: fetch_prices:fetch_prices\n"
                    )
                }
            )
        )
        assert errors_of(report, "reserved-name")

    def test_module_shadowing_stdlib_is_an_error(self):
        """A generated tools/json.py breaks imports for the whole process."""
        report = validate_files(
            agent(
                **{
                    "tools/json.py": "def json_tool(stack=None):\n    pass\n"
                }
            )
        )
        assert errors_of(report, "reserved-name")


class TestVerdictIsOrderIndependent:
    """The same agent must validate the same way whatever else has run.

    ``Tool.registry`` is a mutable process-global: it accumulates every loaded
    agent's tools and test fixtures reset it. Reading it made a shipped agent's
    own tools look like collisions in one test order, and ``builtins.finish``
    look unregistered in another.
    """

    def test_builtins_resolve_with_an_empty_registry(self, monkeypatch):
        """A cleared registry must not make builtins look unregistered."""
        from gimle.hugin.tools.tool import Tool
        from gimle.hugin.utils.registry import Registry

        monkeypatch.setattr(Tool, "registry", Registry())
        report = validate_files(agent())

        assert report["ok"], report["errors"]

    def test_unrelated_registered_tool_is_not_a_collision(self, monkeypatch):
        """Another agent's tool sharing a name must not fail this one."""
        from gimle.hugin.tools.tool import Tool

        monkeypatch.setitem(
            Tool.registry._items, "fetch_prices", object()
        )
        report = validate_files(agent())

        assert report["ok"], report["errors"]


class TestPromptVariables:
    """Warnings only: the renderer namespace is wide and partly dynamic."""

    def test_undeclared_variable_is_warned(self):
        """Nothing supplies '{{ missing }}', so it renders empty."""
        report = validate_files(
            agent(
                **{
                    "tasks/main.yaml": (
                        "name: main\n"
                        "description: Main\n"
                        "prompt: 'Look up {{ missing }}.'\n"
                    )
                }
            )
        )
        assert warnings_of(report, "prompt-variable")

    def test_undeclared_variable_does_not_block(self):
        """A false positive here must never stop a write."""
        report = validate_files(
            agent(
                **{
                    "tasks/main.yaml": (
                        "name: main\n"
                        "description: Main\n"
                        "prompt: 'Look up {{ missing }}.'\n"
                    )
                }
            )
        )
        assert report["ok"]

    def test_parameter_without_dot_value_is_warned(self):
        """'{{ ticker }}' renders the parameter object, not its value."""
        report = validate_files(
            agent(
                **{
                    "tasks/main.yaml": (
                        "name: main\n"
                        "description: Main\n"
                        "parameters:\n"
                        "  ticker:\n"
                        "    type: string\n"
                        "    description: Ticker\n"
                        "prompt: 'Look up {{ ticker }}.'\n"
                    )
                }
            )
        )
        assert warnings_of(report, "prompt-variable")

    def test_pass_result_as_parameter_is_not_warned(self):
        """TaskChain creates these at runtime; warning would be a false alarm."""
        report = validate_files(
            agent(
                **{
                    "tasks/main.yaml": (
                        "name: main\n"
                        "description: Main\n"
                        "pass_result_as: summary\n"
                        "prompt: 'Use {{ summary }}.'\n"
                    )
                }
            )
        )
        assert not warnings_of(report, "prompt-variable")

    def test_renderer_provided_names_are_not_warned(self):
        """'learnings' and friends are injected by the renderer."""
        report = validate_files(
            agent(
                **{
                    "tasks/main.yaml": (
                        "name: main\n"
                        "description: Main\n"
                        "prompt: 'Recall {{ learnings }}.'\n"
                    )
                }
            )
        )
        assert not warnings_of(report, "prompt-variable")


class TestToolContract:
    """A YAML that disagrees with its function fails at call time."""

    def test_missing_function_is_an_error(self):
        """implementation_path names a function the module does not define."""
        report = validate_files(
            agent(
                **{
                    "tools/fetch_prices.py": (
                        "def something_else(stack=None):\n    return {}\n"
                    )
                }
            )
        )
        assert errors_of(report, "tool-contract")

    def test_parameter_the_function_cannot_accept_is_an_error(self):
        """Declaring 'symbol' when the function takes 'ticker' is a TypeError."""
        report = validate_files(
            agent(
                **{
                    "tools/fetch_prices.yaml": (
                        "name: fetch_prices\n"
                        "description: Fetch\n"
                        "parameters:\n"
                        "  symbol:\n"
                        "    type: string\n"
                        "    description: Symbol\n"
                        "implementation_path: fetch_prices:fetch_prices\n"
                    )
                }
            )
        )
        assert errors_of(report, "tool-contract")

    def test_undeclared_required_parameter_is_warned(self):
        """The model cannot supply what the definition does not mention."""
        report = validate_files(
            agent(
                **{
                    "tools/fetch_prices.yaml": (
                        "name: fetch_prices\n"
                        "description: Fetch\n"
                        "implementation_path: fetch_prices:fetch_prices\n"
                    )
                }
            )
        )
        assert warnings_of(report, "tool-contract")

    def test_syntax_error_is_reported_with_a_line(self):
        """Generated Python that does not parse cannot be written."""
        report = validate_files(
            agent(**{"tools/fetch_prices.py": "def broken(:\n    pass\n"})
        )
        assert errors_of(report, "syntax")

    def test_json_schema_style_parameters_are_understood(self):
        """apps/rap_machine declares parameters as a JSON Schema object."""
        report = validate_files(
            agent(
                **{
                    "tools/fetch_prices.yaml": (
                        "name: fetch_prices\n"
                        "description: Fetch\n"
                        "parameters:\n"
                        "  type: object\n"
                        "  properties:\n"
                        "    ticker:\n"
                        "      type: string\n"
                        "      description: Ticker\n"
                        "  required:\n"
                        "    - ticker\n"
                        "implementation_path: fetch_prices:fetch_prices\n"
                    )
                }
            )
        )
        assert report["ok"], report["errors"]


class TestPathKeys:
    """The writer's confinement rules apply before anything reaches disk."""

    def test_traversal_key_is_an_error(self):
        """Caught here as well as in write_agent_files."""
        report = validate_files(agent(**{"../../evil.py": "pwned"}))
        assert errors_of(report, "path")


class TestObservedImports:
    """Missing dependencies are reported, never blocking."""

    def test_third_party_import_is_observed(self):
        """The user needs to know what to install."""
        report = validate_files(
            agent(
                **{
                    "tools/fetch_prices.py": (
                        "import yfinance\n\n\n"
                        "def fetch_prices(ticker, stack=None):\n"
                        "    return {}\n"
                    )
                }
            )
        )
        assert "yfinance" in report["observed_imports"]

    def test_stdlib_import_is_not_observed(self):
        """json is not something to pip install."""
        report = validate_files(
            agent(
                **{
                    "tools/fetch_prices.py": (
                        "import json\n\n\n"
                        "def fetch_prices(ticker, stack=None):\n"
                        "    return {}\n"
                    )
                }
            )
        )
        assert "json" not in report["observed_imports"]

    def test_import_name_is_mapped_to_distribution_name(self):
        """'import yaml' installs PyYAML, not 'yaml'."""
        report = validate_files(
            agent(
                **{
                    "tools/fetch_prices.py": (
                        "import yaml\n\n\n"
                        "def fetch_prices(ticker, stack=None):\n"
                        "    return {}\n"
                    )
                }
            )
        )
        assert "PyYAML" in report["observed_imports"]

    def test_missing_dependency_does_not_block(self):
        """A pandas agent is correct; it just needs pandas installed."""
        report = validate_files(
            agent(
                **{
                    "tools/fetch_prices.py": (
                        "import pandas\n\n\n"
                        "def fetch_prices(ticker, stack=None):\n"
                        "    return {}\n"
                    )
                }
            )
        )
        assert report["ok"]


def _shipped_agent_dirs():
    """Every agent directory the repo ships."""
    found = []
    for root in ("examples", "apps", "src/gimle/hugin/apps"):
        directory = REPO / root
        if not directory.is_dir():
            continue
        for candidate in sorted(directory.iterdir()):
            if candidate.is_dir() and (
                (candidate / "configs").is_dir()
                or (candidate / "tasks").is_dir()
            ):
                found.append(candidate)
    return found


class TestShippedAgentsValidate:
    """The acceptance gate: be right about the framework, not just strict."""

    @pytest.mark.parametrize(
        "agent_dir", _shipped_agent_dirs(), ids=lambda p: p.name
    )
    def test_shipped_agent_has_no_errors(self, agent_dir):
        """A validator that fails these is wrong, and this says which."""
        report = validate_files(collect_files(str(agent_dir)))
        assert report["ok"], report["errors"]

    def test_the_repo_actually_ships_agents_to_check(self):
        """Guards the parametrize above against silently finding nothing."""
        assert len(_shipped_agent_dirs()) > 10
