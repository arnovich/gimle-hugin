"""`--apply`: change the agent, then prove on replay that nothing got worse.

The order is the point. Measure, change, measure again, undo if the second
measurement is worse. An apply that changed code and then reported its own
opinion of the result would be the failure this whole phase exists to avoid --
the agent's verdict on itself is the one number it can always improve by doing
less.
"""

import pytest

from gimle.hugin.analysis.replay import agent_digest, compare_replays
from gimle.hugin.apps.agent_builder.tools.propose_change import (
    MIN_RUNS_FOR_REMOVAL,
)
from gimle.hugin.cli.improve_agent import (
    _instruction_for,
    _restore,
    _snapshot,
)


@pytest.fixture
def agent_dir(tmp_path):
    root = tmp_path / "demo_agent"
    (root / "tools").mkdir(parents=True)
    (root / "configs").mkdir(parents=True)
    (root / "tools" / "fetch.py").write_text("original\n")
    (root / "configs" / "demo.yaml").write_text("name: demo\n")
    return root


class TestTheRevertPath:
    """A revert nobody prepared is a revert that does not happen."""

    def test_a_snapshot_restores_the_edited_file(self, agent_dir):
        backup = _snapshot(agent_dir, ["tools/fetch.py"])
        (agent_dir / "tools" / "fetch.py").write_text("edited\n")

        _restore(agent_dir, backup, ["tools/fetch.py"])

        assert (agent_dir / "tools" / "fetch.py").read_text() == "original\n"

    def test_it_only_touches_the_files_it_snapshotted(self, agent_dir):
        """A revert that restored the whole directory would undo unrelated
        work someone did while the improve run was going."""
        backup = _snapshot(agent_dir, ["tools/fetch.py"])
        (agent_dir / "configs" / "demo.yaml").write_text("name: changed\n")

        _restore(agent_dir, backup, ["tools/fetch.py"])

        assert (agent_dir / "configs" / "demo.yaml").read_text() == (
            "name: changed\n"
        )

    def test_a_missing_file_does_not_break_the_restore(self, agent_dir):
        """A proposal may name a file the edit created rather than changed."""
        backup = _snapshot(agent_dir, ["tools/new.py"])

        assert _restore(agent_dir, backup, ["tools/new.py"]) == []


class TestNothingChangedIsNotSuccess:
    """The reassuring-but-wrong result an apply can produce."""

    def test_identical_agents_are_flagged(self, agent_dir):
        """ "No input changed outcome" across an unchanged agent means the
        apply did nothing, not that the change was safe."""
        digest = agent_digest(str(agent_dir))
        before = {"agent_digest": digest, "results": []}
        after = {"agent_digest": digest, "results": []}

        assert compare_replays(before, after)["same_agent"] is True

    def test_a_real_edit_is_not_flagged(self, agent_dir):
        before = {"agent_digest": agent_digest(str(agent_dir)), "results": []}
        (agent_dir / "tools" / "fetch.py").write_text("edited\n")
        after = {"agent_digest": agent_digest(str(agent_dir)), "results": []}

        assert compare_replays(before, after)["same_agent"] is False

    def test_run_history_does_not_change_the_digest(self, agent_dir):
        """Otherwise every replay would look like an edit, since replaying
        writes traces under the agent."""
        before = agent_digest(str(agent_dir))
        (agent_dir / "storage" / "agents").mkdir(parents=True)
        (agent_dir / "storage" / "agents" / "x").write_text("{}")

        assert agent_digest(str(agent_dir)) == before


class TestTheEditInstruction:
    """Trace-derived prose reaches a write only through a shown diff."""

    def test_it_carries_the_evidence(self):
        instruction = _instruction_for(
            {
                "rationale": "Add a retry.",
                "metric": "tools.fetch.error_rate",
                "observed_value": 0.4,
            }
        )

        assert "Add a retry." in instruction
        assert "tools.fetch.error_rate = 0.4" in instruction

    def test_apply_does_not_pass_yes_to_the_editor(self):
        """The diff-and-confirm in `hugin create --edit` is the guard that
        keeps trace-influenced prose from silently becoming code."""
        import inspect

        from gimle.hugin.cli import improve_agent

        source = inspect.getsource(improve_agent._apply_one)

        assert "--yes" not in source
        assert "--only" in source


class TestRemovingAToolNeedsMoreEvidence:
    """Zero calls is not proof a tool is dead."""

    def test_the_threshold_is_meaningfully_above_a_handful(self):
        assert MIN_RUNS_FOR_REMOVAL >= 20


class TestApplyIsWiredButNotDefault:
    """Propose-only stays the default; apply is opt-in."""

    def test_the_flag_defaults_to_off(self):
        """Read off the real parser, not asserted about in prose."""
        from gimle.hugin.cli.improve_agent import build_parser

        args = build_parser().parse_args(["./some_agent"])

        assert args.apply is False

    def test_the_flag_turns_it_on(self):
        from gimle.hugin.cli.improve_agent import build_parser

        args = build_parser().parse_args(["./some_agent", "--apply"])

        assert args.apply is True

    def test_improve_without_apply_writes_nothing(self):
        """The propose-only path must not reach _guarded_apply."""
        import inspect

        from gimle.hugin.cli import improve_agent

        source = inspect.getsource(improve_agent.main)

        assert "if args.apply:" in source
        assert "_guarded_apply" in source
