"""A proposal has to prove the number it cites.

"Every change must cite a metric" is a prompt norm, and prompt norms produce
*cited* metrics -- including invented ones. By the time a proposal is written
the report is far back in a long single-stack context, which is exactly when a
model reconstructs a plausible number rather than recalling the real one. So
the citation is checked against the stored report instead of requested.
"""

from types import SimpleNamespace

import pytest

from gimle.hugin.apps.agent_builder.tools.propose_change import (
    PROPOSALS_KEY,
    REPORT_KEY,
    propose_change,
)

REPORT = {
    "runs_analyzed": 40,
    "self_reported_success_rate": 0.9,
    "unfinished_rate": 0.1,
    "model_turns": {"p50": 8, "p90": 31, "max": 60},
    "tokens": {"input": 100, "output": 200, "output_per_run": 5.0},
    "tools": [
        {
            "name": "fetch_prices",
            "calls": 120,
            "errors": 48,
            "error_rate": 0.4,
            "max_result_chars": 30000,
            "top_errors": [{"value": "HTTPError: <n>", "count": 40}],
        }
    ],
    "dead_tools": ["summarise_notes"],
    "loops_detected": [{"value": "fetch_prices", "count": 12}],
}


@pytest.fixture
def stack():
    """A stack whose env_vars already hold a trace report."""
    environment = SimpleNamespace(env_vars={REPORT_KEY: dict(REPORT)})
    return SimpleNamespace(agent=SimpleNamespace(environment=environment))


def _propose(stack, **overrides):
    call = {
        "file": "tools/fetch_prices.py",
        "change_type": "edit_tool",
        "metric": "tools.fetch_prices.error_rate",
        "observed_value": "0.4",
        "rationale": "Two in five calls fail; add a retry and a timeout.",
    }
    call.update(overrides)
    return propose_change(stack, **call)


class TestAcceptedCitations:
    """The shapes the report actually has."""

    def test_a_named_row_metric_is_accepted(self, stack):
        assert not _propose(stack).is_error

    def test_a_nested_metric_is_accepted(self, stack):
        response = _propose(
            stack, metric="model_turns.p90", observed_value="31"
        )

        assert not response.is_error

    def test_a_list_metric_is_cited_by_naming_a_member(self, stack):
        response = _propose(
            stack,
            metric="dead_tools",
            observed_value="summarise_notes",
            change_type="remove_tool",
        )

        assert not response.is_error

    def test_a_string_number_matches_a_float(self, stack):
        """Tool arguments arrive as whatever the model emitted."""
        assert not _propose(stack, observed_value="0.400").is_error

    def test_an_accepted_proposal_is_recorded(self, stack):
        _propose(stack)

        recorded = stack.agent.environment.env_vars[PROPOSALS_KEY]
        assert recorded[0]["file"] == "tools/fetch_prices.py"
        assert recorded[0]["observed_value"] == 0.4


class TestRejectedCitations:
    """Each of these is a proposal that reads as well-founded and is not."""

    def test_an_invented_metric_is_rejected(self, stack):
        """The failure mode: a plausible name that is not in the report."""
        response = _propose(stack, metric="tools.fetch_prices.timeout_rate")

        assert response.is_error
        assert "known_metrics" in response.content

    def test_a_metric_for_a_tool_that_does_not_exist_is_rejected(self, stack):
        response = _propose(stack, metric="tools.imaginary_tool.error_rate")

        assert response.is_error

    def test_a_wrong_value_is_rejected(self, stack):
        """Recalling a number instead of reading it is the common case."""
        response = _propose(stack, observed_value="0.9")

        assert response.is_error
        assert response.content["actual_value"] == 0.4

    def test_a_rejected_proposal_is_not_recorded(self, stack):
        _propose(stack, observed_value="0.9")

        assert not stack.agent.environment.env_vars.get(PROPOSALS_KEY)

    def test_an_unknown_change_type_is_rejected(self, stack):
        response = _propose(stack, change_type="rewrite_everything")

        assert response.is_error

    def test_proposing_before_analysing_is_rejected(self):
        """With no report there is nothing to check a citation against."""
        environment = SimpleNamespace(env_vars={})
        bare = SimpleNamespace(agent=SimpleNamespace(environment=environment))

        response = _propose(bare)

        assert response.is_error
        assert "analyze_traces" in response.content["error"]


class TestTheSelfGradeIsNotEvidence:
    """The most dangerous metric in the report, per spec 5.1c.

    `finish_type` is chosen by the agent being measured, so the cheapest way
    to raise the rate is to declare success sooner. It is admissible as a
    symptom and never as evidence that a change is an improvement.
    """

    @pytest.mark.parametrize(
        "metric,value",
        [
            ("self_reported_success_rate", "0.9"),
            ("unfinished_rate", "0.1"),
        ],
    )
    def test_it_is_rejected_even_though_the_value_is_correct(
        self, stack, metric, value
    ):
        """Rejected for what it is, not for being misquoted."""
        response = _propose(stack, metric=metric, observed_value=value)

        assert response.is_error
        assert "own verdict on itself" in response.content["error"]

    def test_the_rejection_says_what_to_cite_instead(self, stack):
        """A rejection with no alternative just produces another guess."""
        response = _propose(
            stack, metric="self_reported_success_rate", observed_value="0.9"
        )

        assert "error rate" in response.content["error"]


class TestCitingAListMetric:
    """Every faithful way of citing a list, accepted.

    Being strict here is not the safe direction: a guard that rejects a
    correct citation teaches the model to abandon real evidence. On a real
    improve run, `loops_detected` was cited accurately and refused three
    times, because each row was compared against the whole stringified list.
    """

    def test_naming_a_row_by_its_value(self, stack):
        response = _propose(
            stack, metric="loops_detected", observed_value="fetch_prices"
        )

        assert not response.is_error

    def test_quoting_the_whole_list_back(self, stack):
        """What the model actually did, and was wrongly refused for."""
        response = _propose(
            stack,
            metric="loops_detected",
            observed_value="[{'value': 'fetch_prices', 'count': 12}]",
        )

        assert not response.is_error

    def test_quoting_a_single_row(self, stack):
        response = _propose(
            stack,
            metric="loops_detected",
            observed_value="{'value': 'fetch_prices', 'count': 12}",
        )

        assert not response.is_error

    def test_a_member_that_is_not_there_is_still_rejected(self, stack):
        """Loosening the match must not make it stop discriminating."""
        response = _propose(
            stack, metric="dead_tools", observed_value="no_such_tool"
        )

        assert response.is_error
