"""Tests for the dreaming provenance forward-scan."""

from gimle.hugin.agent.agent import Agent
from gimle.hugin.agent.config import Config
from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from gimle.hugin.agent.task import Task
from gimle.hugin.artifacts.learning import Learning
from gimle.hugin.artifacts.text import Text
from gimle.hugin.dreaming.provenance import (
    group_by_config,
    scan_provenance,
)

from .memory_storage import MemoryStorage


def _session(storage):
    return Session(environment=Environment(storage=storage))


def _agent_with_insight(session, storage, config_name, task_name, text):
    """Create + persist an agent that saved one Text insight."""
    config = Config(
        llm_model="test-model",
        system_template="system",
        name=config_name,
        description="d",
    )
    task = Task(
        name=task_name,
        description="",
        parameters={},
        prompt="do it",
        tools=[],
    )
    agent = Agent.create_from_task(session, config, task)
    task_def = agent.stack.interactions[0]
    artifact = Text(interaction=task_def, content=text)
    task_def.add_artifact(artifact)
    storage.save_agent(agent)
    return agent, artifact


class TestProvenanceScan:
    """Forward scan attributes episodic artifacts to config/task."""

    def test_attributes_artifact_to_config_and_task(self):
        """An episodic artifact is attributed to its config and task."""
        storage = MemoryStorage()
        _, artifact = _agent_with_insight(
            _session(storage),
            storage,
            "researcher",
            "analyze_sales",
            "Null dates break the parser.",
        )

        provenances = scan_provenance(storage, _session(storage))

        match = [p for p in provenances if p.artifact_id == artifact.id]
        assert len(match) == 1
        assert match[0].config == "researcher"
        assert match[0].task == "analyze_sales"

    def test_groups_by_config(self):
        """Episodic artifacts group by producing config."""
        storage = MemoryStorage()
        session = _session(storage)
        _agent_with_insight(session, storage, "alpha", "t1", "a1")
        _agent_with_insight(session, storage, "alpha", "t2", "a2")
        _agent_with_insight(session, storage, "beta", "t3", "b1")

        groups = group_by_config(scan_provenance(storage, _session(storage)))

        assert set(groups) == {"alpha", "beta"}
        assert len(groups["alpha"]) == 2
        assert len(groups["beta"]) == 1

    def test_excludes_learnings_from_scan(self):
        """Learning artifacts are not episodic input (no dreams-eating-dreams)."""
        storage = MemoryStorage()
        session = _session(storage)
        agent, _ = _agent_with_insight(
            session, storage, "researcher", "analyze", "episodic insight"
        )

        # Attach a Learning to the same interaction and persist it.
        task_def = agent.stack.interactions[0]
        learning = Learning(
            interaction=task_def,
            content="a prior consolidated lesson",
            scope_config="researcher",
        )
        task_def.add_artifact(learning)
        storage.save_agent(agent)

        provenances = scan_provenance(storage, _session(storage))
        ids = {p.artifact_id for p in provenances}
        types = {p.artifact_type for p in provenances}

        assert learning.id not in ids
        assert "Learning" not in types
        assert "Text" in types
