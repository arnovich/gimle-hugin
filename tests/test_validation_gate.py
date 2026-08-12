"""The validation gate must live in code, not in a prompt.

``write_agent_files`` validates the payload itself and refuses to write one
that does not pass. The point of testing it here rather than trusting the
builder's prompt is that a prompt is a request: the model can skip it, and two
instructions already in the builder's own task files (``finalize_agent.yaml``
branching on NEEDS_FIXES, ``test_agent.yaml``'s "maximum 3 fix iterations")
show exactly that happening with nothing enforcing them.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from gimle.hugin.apps.agent_builder.tools.validate_agent import (
    capability_snapshot,
    check_capability_shrink,
    validate_agent,
    validate_with_state,
)
from gimle.hugin.apps.agent_builder.tools.write_agent_files import (
    dump_rejected,
    write_agent_files,
)

VALID = {
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
        "description: Main\n"
        "parameters:\n"
        "  ticker:\n"
        "    type: string\n"
        "    description: Ticker\n"
        "prompt: 'Look up {{ ticker.value }}.'\n"
    ),
    "templates/demo_system.yaml": (
        "name: demo_system\ntemplate: You are a demo agent.\n"
    ),
    "tools/fetch_prices.yaml": (
        "name: fetch_prices\n"
        "description: Fetch\n"
        "parameters:\n"
        "  ticker:\n"
        "    type: string\n"
        "    description: Ticker\n"
        "implementation_path: fetch_prices:fetch_prices\n"
    ),
    "tools/fetch_prices.py": (
        "def fetch_prices(ticker, stack=None):\n    return {}\n"
    ),
}

# The template names a template that does not exist.
BROKEN = dict(VALID)
BROKEN["configs/demo.yaml"] = (
    "name: demo\ndescription: A demo\nsystem_template: no_such_template\n"
)


def make_stack(files):
    """Return a stack stub carrying ``files`` as the generated payload."""
    environment = SimpleNamespace(
        env_vars={
            "generated_files": dict(files),
            "user_input": {
                "agent_name": "demo",
                "description": "A demo agent",
            },
        },
        load_agent_from_path=lambda path: "demo",
    )
    return SimpleNamespace(agent=SimpleNamespace(environment=environment))


class TestGateBlocksInvalidWrites:
    """The headline property of this PR."""

    def test_invalid_payload_is_refused(self, tmp_path):
        """A config pointing at a missing template must not reach disk."""
        result = write_agent_files(
            make_stack(BROKEN), str(tmp_path / "demo"), "demo"
        )
        assert result.is_error

    def test_nothing_is_written_when_refused(self, tmp_path):
        """Refusal means no partial agent, not a half-written one."""
        output = tmp_path / "demo"
        write_agent_files(make_stack(BROKEN), str(output), "demo")
        assert not output.exists()

    def test_refusal_reports_the_errors(self, tmp_path):
        """The model needs to know what to fix, not just that it failed."""
        result = write_agent_files(
            make_stack(BROKEN), str(tmp_path / "demo"), "demo"
        )
        assert result.content["errors"]

    def test_valid_payload_still_writes(self, tmp_path):
        """The gate must not block correct agents."""
        output = tmp_path / "demo"
        result = write_agent_files(make_stack(VALID), str(output), "demo")
        assert not result.is_error, result.content
        assert (output / "configs" / "demo.yaml").exists()

    def test_no_argument_disables_the_gate(self):
        """An escape hatch the model can reach is not a gate."""
        import inspect

        parameters = set(inspect.signature(write_agent_files).parameters)
        assert not parameters & {"force", "skip_validation", "no_validate"}

    def test_tool_definition_exposes_no_bypass(self):
        """The YAML is what the model can actually pass."""
        import yaml

        definition = yaml.safe_load(
            Path(
                "src/gimle/hugin/apps/agent_builder/tools/"
                "write_agent_files.yaml"
            ).read_text()
        )
        assert not set(definition["parameters"]) & {
            "force",
            "skip_validation",
        }


class TestCapabilityShrink:
    """A repair must not pass by deleting what it could not fix."""

    def test_snapshot_records_tools_and_parameters(self):
        """The things a repair can quietly drop."""
        snapshot = capability_snapshot(VALID)
        assert "fetch_prices" in snapshot["tools"]

    def test_unexplained_removal_is_flagged(self):
        """Dropping a tool no error mentioned is not a repair."""
        before = capability_snapshot(VALID)
        after = capability_snapshot(
            {k: v for k, v in VALID.items() if "fetch_prices" not in k}
        )
        findings = check_capability_shrink(after, before, [])
        assert findings

    def test_removal_an_error_asked_for_is_allowed(self):
        """Deleting a tool the validator complained about is legitimate."""
        before = capability_snapshot(VALID)
        after = capability_snapshot(
            {k: v for k, v in VALID.items() if "fetch_prices" not in k}
        )
        errors = [
            {
                "file": "tools/fetch_prices.yaml",
                "check": "tool-contract",
                "message": "fetch_prices is broken beyond repair",
            }
        ]
        assert not check_capability_shrink(after, before, errors)

    def test_gate_blocks_a_write_that_deleted_a_capability(self, tmp_path):
        """End to end: validate, then try to pass by removing the tool."""
        stack = make_stack(BROKEN)
        env_vars = stack.agent.environment.env_vars

        first = write_agent_files(stack, str(tmp_path / "demo"), "demo")
        assert first.is_error

        # "Repair" by deleting the config's tools rather than fixing the
        # template reference.
        env_vars["generated_files"] = dict(VALID)
        del env_vars["generated_files"]["tools/fetch_prices.yaml"]
        del env_vars["generated_files"]["tools/fetch_prices.py"]
        env_vars["generated_files"]["configs/demo.yaml"] = (
            "name: demo\n"
            "description: A demo\n"
            "system_template: demo_system\n"
        )

        second = write_agent_files(stack, str(tmp_path / "demo"), "demo")

        assert second.is_error
        assert any(
            e["check"] == "capability-shrink" for e in second.content["errors"]
        )

    def test_first_validation_has_nothing_to_compare(self):
        """No false positive on the very first attempt."""
        env_vars = {}
        report = validate_with_state(dict(VALID), env_vars)
        assert report["ok"], report["errors"]


class TestRetryDoesNotBypassTheGate:
    """The baseline used to advance on the call that rejected."""

    def test_repeating_the_gutted_payload_stays_refused(self, tmp_path):
        """The refusal literally says "call write_agent_files again"."""
        stack = make_stack(BROKEN)
        env_vars = stack.agent.environment.env_vars
        output = str(tmp_path / "demo")

        assert write_agent_files(stack, output, "demo").is_error

        gutted = dict(VALID)
        del gutted["tools/fetch_prices.yaml"]
        del gutted["tools/fetch_prices.py"]
        gutted["configs/demo.yaml"] = (
            "name: demo\ndescription: A demo\nsystem_template: demo_system\n"
        )
        env_vars["generated_files"] = gutted

        for _ in range(3):
            assert write_agent_files(stack, output, "demo").is_error

    def test_a_real_repair_still_writes(self, tmp_path):
        """Holding the baseline must not wedge the build permanently."""
        stack = make_stack(BROKEN)
        env_vars = stack.agent.environment.env_vars
        output = str(tmp_path / "demo")

        write_agent_files(stack, output, "demo")
        env_vars["generated_files"] = dict(VALID)

        result = write_agent_files(stack, output, "demo")

        assert not result.is_error, result.content
        assert (tmp_path / "demo" / "tools" / "fetch_prices.py").exists()

    def test_shrink_excuse_requires_a_whole_name(self):
        """'search' must not be excused by an error naming 'search_docs'."""
        before = {"tools": ["search", "search_docs"]}
        after = {"tools": ["search_docs"]}
        errors = [
            {
                "file": "c",
                "check": "tool-reference",
                "message": "references unknown tool 'search_docs'",
            }
        ]

        assert check_capability_shrink(after, before, errors)

    def test_naming_the_item_still_excuses_it(self):
        """A genuine authorised removal must keep working."""
        before = {"tools": ["search", "search_docs"]}
        after = {"tools": ["search_docs"]}
        errors = [
            {
                "file": "c",
                "check": "tool-reference",
                "message": "references unknown tool 'search'",
            }
        ]

        assert not check_capability_shrink(after, before, errors)

    def test_renaming_a_config_is_not_a_shrink(self):
        """Renaming is the natural repair for a name collision."""
        before = {"config-tools:configs/demo.yaml": ["alpha", "beta"]}
        after = {"config-tools:configs/renamed.yaml": ["alpha", "beta"]}

        assert not check_capability_shrink(after, before, [])


class TestValidatingAnotherAgentIsIsolated:
    """agent_path is exposed to the model and shares env_vars."""

    def test_validating_a_path_does_not_poison_the_build(self, tmp_path):
        """It used to store a foreign baseline with no way to recover."""
        other = tmp_path / "other"
        (other / "configs").mkdir(parents=True)
        (other / "tasks").mkdir()
        (other / "configs" / "other.yaml").write_text(
            "name: other\ndescription: x\nsystem_template: Inline prompt.\n"
        )
        (other / "tasks" / "t.yaml").write_text(
            "name: t\ndescription: x\nprompt: go\n"
        )

        stack = make_stack(VALID)
        validate_agent(stack, agent_path=str(other))

        result = write_agent_files(stack, str(tmp_path / "demo"), "demo")

        assert not result.is_error, result.content


class TestNoPreReviewWrite:
    """validate_agent must not write the agent behind the reviewer's back."""

    def test_clean_validation_does_not_chain_into_a_write(self, tmp_path):
        """build_agent's prompt says writing happens after review."""
        stack = make_stack(VALID)

        result = validate_agent(stack)

        assert not result.is_error
        assert result.next_tool is None


class TestAttemptCounter:
    """The bound lives in code; task_sequence cannot loop."""

    def test_attempts_increment(self):
        """Each validation is counted, in env_vars rather than in prose."""
        env_vars = {}
        validate_with_state(dict(VALID), env_vars)
        report = validate_with_state(dict(VALID), env_vars)
        assert report["attempt"] == 2

    def test_state_survives_in_env_vars(self):
        """So any tool in the build can see how many tries have happened."""
        env_vars = {}
        validate_with_state(dict(VALID), env_vars)
        assert env_vars["validation_state"]["attempts"] == 1


class TestRejectedPayload:
    """A failed build must leave something actionable behind."""

    def test_payload_is_written_beside_the_target(self, tmp_path):
        """Beside, never inside -- the target must stay untouched."""
        output = tmp_path / "demo"
        path = dump_rejected(dict(BROKEN), str(output))

        assert path == f"{output}.rejected"
        assert not output.exists()
        assert (Path(path) / "configs" / "demo.yaml").exists()

    def test_report_explains_the_failure(self, tmp_path):
        """A bare failure is not actionable; the errors are."""
        path = dump_rejected(dict(BROKEN), str(tmp_path / "demo"))
        report = (Path(path) / "VALIDATION_REPORT.md").read_text()

        assert "no_such_template" in report
        assert "hugin validate" in report

    def test_nothing_generated_writes_nothing(self, tmp_path):
        """No empty .rejected directory when there was no payload."""
        assert dump_rejected({}, str(tmp_path / "demo")) is None

    def test_traversal_key_is_not_written(self, tmp_path):
        """The rejected dump is confined like every other write."""
        payload = dict(BROKEN)
        payload["../../escape.py"] = "pwned"
        path = dump_rejected(payload, str(tmp_path / "demo"))

        assert not (tmp_path.parent / "escape.py").exists()
        assert Path(path).exists()


class TestReviewerNoLongerDuplicatesTheValidator:
    """Review time should go to what a machine cannot judge."""

    @pytest.fixture
    def reviewer(self):
        """Return the reviewer template as one whitespace-normalised line.

        The body is hard-wrapped, so asserting on a phrase would otherwise
        break whenever a sentence happens to straddle a line.
        """
        import yaml

        body = yaml.safe_load(
            Path(
                "src/gimle/hugin/apps/agent_builder/templates/"
                "reviewer_system.yaml"
            ).read_text()
        )["template"]
        return " ".join(body.split())

    def test_reviewer_focuses_on_description_alignment(self, reviewer):
        """The one thing the validator cannot check."""
        assert "does this agent actually do what the user asked" in reviewer

    def test_reviewer_no_longer_checks_python_syntax(self, reviewer):
        """Now guaranteed mechanically before any write."""
        assert "Valid Python Syntax" not in reviewer

    def test_reviewer_is_told_not_to_recheck_mechanics(self, reviewer):
        """Otherwise the real problem gets missed."""
        assert "Do not re-check" in reviewer
