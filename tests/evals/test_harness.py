"""Tests for the golden-set eval harness.

The harness measures a model, so most of it cannot be asserted cheaply. What
*can* be pinned without spending anything is the part that decides what a run
means: the scoring of a produced directory, the aggregation across cases, and
the comparison that would gate a prompt change. Those are the pieces a wrong
answer would quietly corrupt, so those are what is tested here.

The one end-to-end case is marked ``slow`` and skips without an API key.
"""

import json
import os
from pathlib import Path

import pytest

from tests.evals.golden_set import GOLDEN_SET, by_name, select
from tests.evals.harness import (
    compare,
    score_output,
    summarise,
    write_report,
)


def write_agent(root: Path, *, tools=1, task_sequence=False, broken=False):
    """Write a small generated-agent directory to score."""
    (root / "configs").mkdir(parents=True, exist_ok=True)
    (root / "tasks").mkdir(exist_ok=True)
    (root / "templates").mkdir(exist_ok=True)
    (root / "tools").mkdir(exist_ok=True)

    tool_names = [f"tool_{index}" for index in range(tools)]
    granted = "\n".join(f"  - {name}" for name in tool_names)
    (root / "configs" / "demo.yaml").write_text(
        "name: demo\ndescription: A demo\nsystem_template: demo_system\n"
        f"tools:\n{granted}\n  - builtins.finish:finish\n"
    )
    chain = "task_sequence: [second]\n" if task_sequence else ""
    (root / "tasks" / "main.yaml").write_text(
        f"name: main\ndescription: Main\n{chain}prompt: Do the thing.\n"
    )
    if task_sequence:
        (root / "tasks" / "second.yaml").write_text(
            "name: second\ndescription: Second\nprompt: Then this.\n"
        )
    (root / "templates" / "demo_system.yaml").write_text(
        "name: demo_system\ntemplate: You are a demo agent.\n"
    )
    for name in tool_names:
        (root / "tools" / f"{name}.yaml").write_text(
            f"name: {name}\ndescription: A tool\n"
            f"implementation_path: {name}:{name}\n"
        )
        body = (
            "def wrong_name(stack=None):\n    return {}\n"
            if broken
            else f"def {name}(stack=None):\n    return {{}}\n"
        )
        (root / "tools" / f"{name}.py").write_text(body)


class TestGoldenSet:
    """The set is the measurement instrument; it has to be well formed."""

    def test_names_are_unique(self):
        """Reports are keyed by name."""
        names = [case.name for case in GOLDEN_SET]
        assert len(names) == len(set(names))

    def test_names_are_valid_agent_names(self):
        """They are passed straight to `hugin create --name`."""
        for case in GOLDEN_SET:
            assert case.name.replace("_", "").isalnum(), case.name
            assert case.name.islower(), case.name

    def test_descriptions_are_substantial(self):
        """A one-word description measures nothing."""
        for case in GOLDEN_SET:
            assert len(case.description) > 60, case.name

    def test_the_intended_architectures_are_covered(self):
        """The set exists to span shapes, not just count cases."""
        covered = {case.expect_architecture for case in GOLDEN_SET}
        assert {"single_shot", "pipeline", "delegating"} <= covered

    def test_a_cheap_case_exists(self):
        """There has to be a way to smoke-test for a few cents."""
        assert select(tag="cheap")

    def test_by_name_reports_the_alternatives(self):
        """A typo should not be a dead end."""
        with pytest.raises(KeyError) as excinfo:
            by_name("no_such_case")
        assert "unit_converter" in str(excinfo.value)

    def test_select_limits(self):
        """Running everything is expensive; subsets are the normal path."""
        assert len(select(limit=3)) == 3


class TestScoring:
    """What a produced directory is worth."""

    def test_a_valid_agent_scores_as_validating(self, tmp_path):
        """The baseline every other case is measured against."""
        write_agent(tmp_path)

        score = score_output(by_name("unit_converter"), tmp_path)

        assert score["built"] and score["validates"]

    def test_a_broken_tool_fails_validation(self, tmp_path):
        """Scoring must use the real validator, not a proxy for it."""
        write_agent(tmp_path, broken=True)

        score = score_output(by_name("unit_converter"), tmp_path)

        assert score["built"] and not score["validates"]
        assert "tool-contract" in score["error_checks"]

    def test_a_missing_directory_is_not_built(self, tmp_path):
        """A refused build leaves nothing, and that is a distinct outcome."""
        score = score_output(by_name("unit_converter"), tmp_path / "absent")

        assert score["built"] is False

    def test_tool_expectation_is_checked(self, tmp_path):
        """A case asking for two tools is not satisfied by one."""
        write_agent(tmp_path, tools=1)

        score = score_output(by_name("weather_advisor"), tmp_path)

        assert score["meets_tool_expectation"] is False

    def test_pipeline_shape_is_detected(self, tmp_path):
        """A structural proxy, usable before architecture selection exists."""
        write_agent(tmp_path, task_sequence=True)

        assert score_output(by_name("research_pipeline"), tmp_path)[
            "has_task_sequence"
        ]

    def test_flat_agent_is_not_a_pipeline(self, tmp_path):
        """The proxy must discriminate, or it measures nothing."""
        write_agent(tmp_path)

        assert not score_output(by_name("research_pipeline"), tmp_path)[
            "has_task_sequence"
        ]


class TestAggregation:
    """The numbers that get compared between runs."""

    def test_rates_are_computed(self):
        """Two of three validating is a validation rate of 0.667."""
        rows = [
            {"built": True, "validates": True},
            {"built": True, "validates": True},
            {"built": True, "validates": False},
        ]

        summary = summarise(rows)

        assert summary["validation_rate"] == 0.667
        assert summary["build_rate"] == 1.0

    def test_failing_checks_are_collected(self):
        """Which check failed is what points at the fix."""
        rows = [{"error_checks": ["tool-contract"]}, {"error_checks": ["yaml"]}]

        assert summarise(rows)["failing_checks"] == ["tool-contract", "yaml"]

    def test_empty_run_does_not_divide_by_zero(self):
        """A selection matching nothing must not crash the report."""
        assert summarise([])["cases"] == 0

    def test_tokens_are_totalled(self):
        """Cost is a first-class number here, not an afterthought."""
        rows = [{"output_tokens": 100}, {"output_tokens": 250}]

        assert summarise(rows)["output_tokens"] == 350


class TestComparison:
    """The point of the harness: did a change help or hurt."""

    def _report(self, **summary):
        """Wrap a summary in report shape."""
        return {"summary": summary, "rows": []}

    def test_an_improvement_is_reported(self):
        """The case the harness exists for."""
        lines = compare(
            self._report(validation_rate=0.6),
            self._report(validation_rate=0.9),
        )

        assert any("0.6 -> 0.9" in line for line in lines)

    def test_a_regression_is_reported(self):
        """Gating a prompt change needs this direction to show too."""
        lines = compare(
            self._report(validation_rate=0.9),
            self._report(validation_rate=0.6),
        )

        assert any("0.9 -> 0.6" in line for line in lines)

    def test_no_change_says_so(self):
        """Silence would read as 'not measured'."""
        lines = compare(
            self._report(validation_rate=0.9),
            self._report(validation_rate=0.9),
        )

        assert lines == ["no change in the compared metrics"]


class TestReportRoundTrip:
    """A report only has value if it can be compared later."""

    def test_written_report_reloads(self, tmp_path):
        """--out then --baseline is the whole workflow."""
        report = {"summary": {"validation_rate": 0.8}, "rows": []}
        path = tmp_path / "nested" / "report.json"

        write_report(report, path)

        assert json.loads(path.read_text()) == report


@pytest.mark.slow
@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="needs a real model; the harness measures a model",
)
def test_one_real_build(tmp_path):
    """Smoke-test the whole path on the cheapest case.

    Deliberately one case: this spends real money, and the harness's value is
    in being run deliberately rather than on every commit.
    """
    from tests.evals.harness import run_case

    row = run_case(by_name("unit_converter"), tmp_path, timeout=600)

    assert row["built"], row.get("tail")
    assert row["validates"], row.get("error_checks")
