"""Replay: re-run an agent on inputs it actually saw.

`analyze_traces` says what an agent did. It cannot say whether a change helped,
because the rewritten agent has no history to compare against. Replay is the
missing half.

The security property is the interesting one. The rest of `analysis` exists to
produce something safe to hand a model -- arguments hashed, errors reduced to
signatures, every string redacted. Replay needs the opposite: the real values,
or it is not replaying anything. So the two must not meet.
"""

import json

import pytest

from gimle.hugin.analysis.replay import (
    compare_replays,
    fingerprint,
    harvest_inputs,
)
from gimle.hugin.analysis.traces import analyze_traces

SECRET = "sk-live-zzTOPsecretKEYvaluezz"


def _write_run(storage, run_id, task_name, parameters, finish="success"):
    """Persist a minimal but realistic run to a storage directory."""
    agents = storage / "agents"
    interactions = storage / "interactions"
    agents.mkdir(parents=True, exist_ok=True)
    interactions.mkdir(parents=True, exist_ok=True)

    ids = []

    def add(kind, data):
        uuid = f"{run_id}-{len(ids)}"
        (interactions / uuid).write_text(
            json.dumps({"type": kind, "data": data})
        )
        ids.append(uuid)

    add(
        "TaskDefinition",
        {
            "task": {
                "name": task_name,
                "description": "d",
                "prompt": "p",
                "parameters": parameters,
            }
        },
    )
    add("TaskResult", {"finish_type": finish, "branch": None})
    (agents / run_id).write_text(
        json.dumps(
            {
                "uuid": run_id,
                "config": {"name": "demo_agent", "tools": []},
                "stack": {"interactions": ids},
            }
        )
    )


@pytest.fixture
def storage(tmp_path):
    """Two runs with different inputs, one of them carrying a credential."""
    root = tmp_path / "storage"
    _write_run(
        root,
        "run-1",
        "check",
        {"ticker": {"type": "string", "description": "t", "value": "AAPL"}},
    )
    _write_run(
        root,
        "run-2",
        "check",
        {
            "ticker": {"type": "string", "description": "t", "value": "MSFT"},
            "api_key": {"type": "string", "description": "k", "value": SECRET},
        },
    )
    return root


class TestHarvesting:
    """What comes out, and in what shape."""

    def test_it_finds_the_inputs_runs_actually_used(self, storage):
        inputs = harvest_inputs(str(storage))

        tickers = {item["parameters"].get("ticker") for item in inputs}
        assert tickers == {"AAPL", "MSFT"}

    def test_it_keeps_the_real_values(self, storage):
        """A replay with schema defaults instead of values replays nothing."""
        inputs = harvest_inputs(str(storage))

        assert all(
            isinstance(item["parameters"].get("ticker"), str) for item in inputs
        )

    def test_identical_input_sets_are_deduplicated(self, tmp_path):
        """Ten runs of the same input are one replay, not ten."""
        root = tmp_path / "storage"
        for index in range(5):
            _write_run(
                root,
                f"run-{index}",
                "check",
                {
                    "ticker": {
                        "type": "string",
                        "description": "t",
                        "value": "AAPL",
                    }
                },
            )

        assert len(harvest_inputs(str(root))) == 1

    def test_it_caps_how_many_it_returns(self, tmp_path):
        """A replay is a regression check, not a second eval suite."""
        root = tmp_path / "storage"
        for index in range(8):
            _write_run(
                root,
                f"run-{index}",
                "check",
                {
                    "ticker": {
                        "type": "string",
                        "description": "t",
                        "value": f"T{index}",
                    }
                },
            )

        assert len(harvest_inputs(str(root), max_inputs=3)) == 3


class TestValuesNeverReachAModel:
    """The property that keeps the two halves of `analysis` apart.

    Harvested values are raw user input, by necessity. The analysis report is
    built to be shown to a model. If the entry task's parameters leaked into
    the report, every credential a run was given would travel with it.
    """

    def test_the_analysis_report_carries_no_parameter_values(self, storage):
        report = analyze_traces(str(storage))

        assert SECRET not in json.dumps(report)
        assert "AAPL" not in json.dumps(report)

    def test_the_harvest_does_carry_them(self, storage):
        """The counterpart: without this the test above proves nothing."""
        inputs = harvest_inputs(str(storage))

        assert SECRET in json.dumps(inputs)

    def test_a_fingerprint_does_not_reveal_the_value(self, storage):
        """Reports quote fingerprints so they can be pasted anywhere."""
        digest = fingerprint({"api_key": SECRET})

        assert SECRET not in digest
        assert len(digest) == 12

    def test_the_fingerprint_is_stable_across_key_order(self):
        """Otherwise a before/after comparison matches nothing."""
        assert fingerprint({"a": 1, "b": 2}) == fingerprint({"b": 2, "a": 1})


class TestComparison:
    """Before and after, matched by input rather than by totals."""

    def _report(self, *outcomes):
        return {
            "results": [
                {
                    "fingerprint": f"fp{index}",
                    "task": "check",
                    "finished": finished,
                    "finish_type": "success" if finished else None,
                    "model_turns": turns,
                }
                for index, (finished, turns) in enumerate(outcomes)
            ]
        }

    def test_an_input_that_stopped_finishing_is_a_regression(self):
        comparison = compare_replays(
            self._report((True, 5)), self._report((False, 9))
        )

        assert len(comparison["regressions"]) == 1

    def test_an_input_that_started_finishing_is_an_improvement(self):
        comparison = compare_replays(
            self._report((False, 9)), self._report((True, 5))
        )

        assert len(comparison["improvements"]) == 1

    def test_unchanged_outcomes_are_neither(self):
        comparison = compare_replays(
            self._report((True, 5)), self._report((True, 8))
        )

        assert not comparison["regressions"]
        assert not comparison["improvements"]

    def test_turn_count_alone_is_not_a_verdict(self):
        """Fewer turns can mean "did less", which is the Goodhart move.

        The verdict is finished/not; turns ride alongside for a human.
        """
        comparison = compare_replays(
            self._report((True, 20)), self._report((True, 3))
        )

        assert comparison["rows"][0]["verdict"] == "unchanged"
        assert comparison["rows"][0]["turns_delta"] == -17

    def test_inputs_present_on_only_one_side_are_reported(self):
        """Comparing different input sets must not silently compare totals."""
        before = self._report((True, 5), (True, 5))
        after = self._report((True, 5))

        comparison = compare_replays(before, after)

        assert comparison["unmatched_before"] == ["fp1"]
        assert comparison["compared"] == 1


class TestAProviderOutageIsNotARegression:
    """The failure mode that makes an automated apply loop dangerous.

    An outage and an agent doing badly look identical from outside: the run did
    not finish. Scored as an outcome, a billing lapse reads as a regression --
    and in an apply loop would revert a change that was fine. This was already
    learned once on the eval harness, where an exhausted balance scored 11 of
    15 builds as failures and reported zero infrastructure failures.
    """

    def _results(self, *rows):
        return {
            "results": [
                {
                    "fingerprint": f"fp{index}",
                    "task": "check",
                    "finished": finished,
                    "finish_type": "success" if finished else None,
                    "model_turns": 1,
                    "provider_failure": outage,
                }
                for index, (finished, outage) in enumerate(rows)
            ]
        }

    def test_an_outage_is_not_compared(self):
        """It says nothing about the agent, so it cannot be a verdict."""
        comparison = compare_replays(
            self._results((True, False)), self._results((False, True))
        )

        assert not comparison["regressions"]
        assert comparison["compared"] == 0

    def test_a_real_failure_next_to_an_outage_still_counts(self):
        """Excluding outages must not excuse genuine regressions."""
        before = self._results((True, False), (True, False))
        after = self._results((False, True), (False, False))

        comparison = compare_replays(before, after)

        assert len(comparison["regressions"]) == 1
        assert comparison["regressions"][0]["fingerprint"] == "fp1"


class TestClassificationIsSharedWithTheEval:
    """One list, two consumers, so they cannot drift."""

    def test_the_eval_harness_uses_the_same_judgement(self):
        from gimle.hugin.analysis.provider_errors import is_provider_failure
        from tests.evals.harness import is_infrastructure_failure

        outage = "Your credit balance is too low to access the Anthropic API."

        assert is_provider_failure(outage)
        assert is_infrastructure_failure(outage)

    def test_a_real_agent_failure_is_neither(self):
        from gimle.hugin.analysis.provider_errors import is_provider_failure

        assert not is_provider_failure(
            "tool-contract: parameter 'x' is declared but not accepted"
        )
