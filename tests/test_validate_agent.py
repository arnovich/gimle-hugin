"""Tests for the agent builder's static validator.

Two obligations, and the second is the one that matters. The validator must
catch each class of breakage (one deliberately broken fixture per check), and
it must stay silent on the repo's own agents -- a validator that fails the
shipped examples is wrong about the framework, not right about the examples.
"""

import argparse
import inspect
from pathlib import Path

import pytest
import yaml

from gimle.hugin.apps.agent_builder.tools.validate_agent import (
    AgentReadError,
    collect_files,
    validate_agent,
    validate_files,
)
from gimle.hugin.cli.cli import cmd_validate

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


def write_agent(root, files=None):
    """Write an agent fixture to disk for CLI and confinement tests."""
    for key, content in (files or agent()).items():
        path = root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


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

    @pytest.mark.parametrize(
        "implementation_path",
        [None, "broken", "broken:", ":broken", 3],
    )
    def test_invalid_implementation_path_is_an_error(self, implementation_path):
        """A validator pass must mean Tool can load the advertised callable."""
        lines = ["name: fetch_prices", "description: Fetch"]
        if implementation_path is not None:
            lines.append(f"implementation_path: {implementation_path!r}")
        report = validate_files(
            agent(
                **{
                    "tools/fetch_prices.yaml": "\n".join(lines) + "\n",
                }
            )
        )
        assert errors_of(report, "tool-definition")

    def test_helper_module_without_a_definition_is_allowed(self):
        """Shared helper modules are a normal pattern, not a defect."""
        report = validate_files(agent(**{"tools/helpers.py": "VALUE = 1\n"}))
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

    @pytest.mark.parametrize(
        "tools_yaml",
        [
            "tools: 3\n",
            "tools: broken\n",
            "tools:\n  - 3\n",
            "tools:\n  - ''\n",
        ],
    )
    def test_malformed_tools_field_is_one_schema_error(self, tools_yaml):
        """Malformed generated tool grants must not crash or silently pass."""
        report = validate_files(
            agent(
                **{
                    "configs/demo.yaml": (
                        "name: demo\n"
                        "description: A demo\n"
                        "system_template: demo_system\n"
                        f"{tools_yaml}"
                    )
                }
            )
        )
        assert len(errors_of(report, "tool-schema")) == 1


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
            agent(**{"tools/json.py": "def json_tool(stack=None):\n    pass\n"})
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

        monkeypatch.setitem(Tool.registry._items, "fetch_prices", object())
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
        """Task chaining creates these at runtime; a warning would be wrong."""
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


class TestImplementationPathSpellings:
    """Tool._load_implementation accepts two forms, so the checker must too."""

    def test_dotted_form_is_contract_checked(self):
        """The dotted form used to yield an empty function name.

        That empty name then made _check_tool_contracts skip the file
        entirely, so apps/financial_newspaper passed the acceptance gate with
        no contract check ever running.
        """
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
                        "implementation_path: fetch_prices.fetch_prices\n"
                    )
                }
            )
        )
        assert errors_of(report, "tool-contract")

    def test_dotted_form_accepts_a_correct_tool(self):
        """Being checked must not mean being rejected."""
        report = validate_files(
            agent(
                **{
                    "tools/fetch_prices.yaml": (
                        "name: fetch_prices\n"
                        "description: Fetch\n"
                        "parameters:\n"
                        "  ticker:\n"
                        "    type: string\n"
                        "    description: Ticker\n"
                        "implementation_path: fetch_prices.fetch_prices\n"
                    )
                }
            )
        )
        assert report["ok"], report["errors"]


class TestMalformedYaml:
    """A YAML file may parse to a list or scalar; .get() then explodes."""

    def test_list_shaped_tool_definition_is_reported(self):
        """Previously an AttributeError escaped and aborted the run."""
        report = validate_files(
            agent(**{"tools/fetch_prices.yaml": "- name: fetch_prices\n"})
        )
        assert errors_of(report, "yaml")

    def test_list_shaped_task_parameters_are_reported(self):
        """The writer calls the validator, so this crashed the write too."""
        report = validate_files(
            agent(
                **{
                    "tasks/main.yaml": (
                        "name: main\n"
                        "description: Main\n"
                        "parameters:\n"
                        "  - topic\n"
                        "prompt: 'Do {{ topic }}.'\n"
                    )
                }
            )
        )
        assert not report["ok"]

    def test_scalar_task_file_is_reported(self):
        """A whole file that is just a string must not raise."""
        report = validate_files(agent(**{"tasks/main.yaml": "just a string\n"}))
        assert errors_of(report, "yaml")

    def test_unparseable_tool_yaml_is_reported(self):
        """Only configs/ and tasks/ parse errors used to surface."""
        report = validate_files(
            agent(**{"tools/fetch_prices.yaml": "name: [unclosed\n"})
        )
        assert errors_of(report, "yaml")

    def test_unparseable_template_is_reported(self):
        """A corrupt template killed Environment.load, not validation."""
        report = validate_files(
            agent(**{"templates/demo_system.yaml": "name: [unclosed\n"})
        )
        assert errors_of(report, "yaml")


class TestTaskParameterSchemas:
    """The validator must not pass what Task itself refuses to construct."""

    def test_scalar_parameter_form_is_an_error(self):
        """CLAUDE.md documents it, so the builder emits it, and Task rejects it."""
        report = validate_files(
            agent(
                **{
                    "tasks/main.yaml": (
                        "name: main\n"
                        "description: Main\n"
                        "parameters:\n"
                        '  topic: "AI"\n'
                        "prompt: 'Write about {{ topic.value }}.'\n"
                    )
                }
            )
        )
        assert errors_of(report, "task-parameters")

    def test_schema_missing_description_is_an_error(self):
        """Task requires both type and description."""
        report = validate_files(
            agent(
                **{
                    "tasks/main.yaml": (
                        "name: main\n"
                        "description: Main\n"
                        "parameters:\n"
                        "  topic:\n"
                        "    type: string\n"
                        "prompt: 'Write {{ topic.value }}.'\n"
                    )
                }
            )
        )
        assert errors_of(report, "task-parameters")

    def test_a_validated_task_can_actually_be_constructed(self):
        """The property that matters: passing means loadable."""
        import yaml as yaml_module

        from gimle.hugin.agent.task import Task

        files = agent()
        assert validate_files(files)["ok"]
        document = yaml_module.safe_load(files["tasks/main.yaml"])
        Task(
            name=document["name"],
            description=document["description"],
            parameters=document["parameters"],
            prompt=document["prompt"],
        )


class TestVarKeywordTools:
    """**kwargs tools are an explicitly supported framework pattern."""

    def test_kwargs_tool_is_accepted(self):
        """Tool.execute_tool computes accepts_varkw and passes them through."""
        report = validate_files(
            agent(
                **{
                    "tools/fetch_prices.py": (
                        "def fetch_prices(stack=None, **kwargs):\n"
                        "    return {}\n"
                    )
                }
            )
        )
        assert report["ok"], report["errors"]


class TestBareTemplateReferenceInPrompt:
    """A prompt expands a bare template name exactly as system_template does."""

    def test_typo_in_a_prompt_reference_is_an_error(self):
        """Otherwise the literal string renders instead of the template body."""
        report = validate_files(
            agent(
                **{
                    "tasks/main.yaml": (
                        "name: main\ndescription: Main\nprompt: demo_sytsem\n"
                    )
                }
            )
        )
        assert errors_of(report, "template-reference")

    def test_valid_prompt_reference_is_accepted(self):
        """The documented bare-name form must keep working."""
        report = validate_files(
            agent(
                **{
                    "tasks/main.yaml": (
                        "name: main\ndescription: Main\nprompt: demo_system\n"
                    )
                }
            )
        )
        assert not errors_of(report, "template-reference")


class TestPathKeys:
    """The writer's confinement rules apply before anything reaches disk."""

    def test_traversal_key_is_an_error(self):
        """Caught here as well as in write_agent_files."""
        report = validate_files(agent(**{"../../evil.py": "pwned"}))
        assert errors_of(report, "path")


class TestOnDiskCollection:
    """CLI validation must not escape its root or read without limits."""

    def test_symlinked_agent_folder_is_rejected(self, tmp_path):
        """A configs symlink must never expose files outside the agent."""
        root = tmp_path / "agent"
        outside = tmp_path / "outside"
        root.mkdir()
        outside.mkdir()
        (outside / "secret.yaml").write_text("secret: value\n")
        (root / "configs").symlink_to(outside, target_is_directory=True)

        with pytest.raises(AgentReadError):
            collect_files(str(root))

    def test_symlinked_agent_file_is_rejected(self, tmp_path):
        """A YAML symlink must not be opened even inside a real folder."""
        root = tmp_path / "agent"
        outside = tmp_path / "secret.yaml"
        (root / "configs").mkdir(parents=True)
        outside.write_text("secret: value\n")
        (root / "configs" / "demo.yaml").symlink_to(outside)

        with pytest.raises(AgentReadError):
            collect_files(str(root))

    def test_file_size_is_bounded(self, tmp_path):
        """One oversized generated file cannot exhaust validator memory."""
        root = tmp_path / "agent"
        (root / "configs").mkdir(parents=True)
        (root / "configs" / "demo.yaml").write_text("12345")

        with pytest.raises(AgentReadError):
            collect_files(str(root), max_file_bytes=4)

    def test_file_count_is_bounded(self, tmp_path):
        """The shared budget applies across all agent subdirectories."""
        root = tmp_path / "agent"
        (root / "configs").mkdir(parents=True)
        (root / "tasks").mkdir()
        (root / "configs" / "demo.yaml").write_text("a")
        (root / "tasks" / "main.yaml").write_text("b")

        with pytest.raises(AgentReadError):
            collect_files(str(root), max_files=1)

    def test_total_bytes_are_bounded(self, tmp_path):
        """Many individually small files still share one byte budget."""
        root = tmp_path / "agent"
        (root / "configs").mkdir(parents=True)
        (root / "tasks").mkdir()
        (root / "configs" / "demo.yaml").write_text("1234")
        (root / "tasks" / "main.yaml").write_text("5678")

        with pytest.raises(AgentReadError):
            collect_files(str(root), max_bytes=7, max_file_bytes=4)


class TestModelFacingValidator:
    """The builder tool validates generated state, never arbitrary disk paths."""

    def test_agent_path_is_not_a_tool_parameter(self):
        """Disk access belongs to the explicit CLI caller only."""
        assert "agent_path" not in inspect.signature(validate_agent).parameters

        definition = yaml.safe_load(
            (
                REPO
                / "src/gimle/hugin/apps/agent_builder/tools/validate_agent.yaml"
            ).read_text()
        )
        assert "agent_path" not in definition["parameters"]


class TestValidateCli:
    """Every explicitly requested recursive root is part of the CI gate."""

    def test_missing_root_fails_even_when_another_root_has_agents(
        self, tmp_path, capsys
    ):
        """One valid root must not hide another root being deleted or renamed."""
        parent = tmp_path / "agents"
        write_agent(parent / "demo")
        missing = tmp_path / "missing"
        args = argparse.Namespace(
            paths=[str(parent), str(missing)], recursive=True, quiet=True
        )

        assert cmd_validate(args) == 1
        output = capsys.readouterr().out
        assert f"error {missing}: not a directory" in output
        assert f"OK   {parent / 'demo'}" in output


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
        """The json module is not something to pip install."""
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
