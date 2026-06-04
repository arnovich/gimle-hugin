"""Attribute episodic artifacts to the config/task that produced them.

Forward scan: walk persisted agents (each carries its config, its ordered
interaction UUIDs, and its config-state history) to build an
``interaction_uuid -> (config, task)`` index, then join the raw artifact records
(which carry their producing interaction's UUID) to it. This works retroactively
over the existing corpus with no change to the write path.

A persisted interaction has no back-pointer to its agent, so the join goes
through the agent scan rather than artifact -> interaction -> agent in isolation.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from gimle.hugin.agent.agent import Agent
from gimle.hugin.agent.session import Session
from gimle.hugin.interaction.task_definition import TaskDefinition
from gimle.hugin.storage.storage import Storage

logger = logging.getLogger(__name__)

# Artifact types that are dream output, not episodic memory. Excluded from the
# dream's own input (no dreams-eating-dreams).
LEARNING_TYPE = "Learning"

Scope = Tuple[Optional[str], Optional[str]]


@dataclass
class ArtifactProvenance:
    """The config/task an episodic artifact was produced under."""

    artifact_id: str
    artifact_type: str
    config: Optional[str]
    task: Optional[str]
    interaction_id: Optional[str]


def _config_by_position(agent: Agent) -> Dict[int, Optional[str]]:
    """Map each stack position to the config active when it was created.

    Agents without a config state machine ran under a single config for their
    whole life. State-machine agents switched configs mid-run; ``_config_history``
    records, per transition, the interaction after which the new state took
    effect — so an interaction at position ``p`` ran under the most recent
    transition recorded strictly before ``p``.
    """
    interactions = agent.stack.interactions
    n = len(interactions)
    final_config = agent.config.name
    history = agent.config_history
    if not history:
        return {i: final_config for i in range(n)}

    positions = {str(it.uuid): i for i, it in enumerate(interactions)}
    transitions: List[Tuple[int, Optional[str]]] = []
    for entry in history:
        interaction_id = entry.get("interaction_id")
        state = entry.get("state")
        if interaction_id is None:
            transition_position = -1  # initial state, applies from the start
        else:
            resolved = positions.get(str(interaction_id))
            if resolved is None:
                continue
            transition_position = resolved
        transitions.append((transition_position, state))
    transitions.sort(key=lambda t: t[0])

    result: Dict[int, Optional[str]] = {}
    for position in range(n):
        active: Optional[str] = final_config
        for transition_position, state in transitions:
            if transition_position < position:
                active = state
            else:
                break
        result[position] = active
    return result


def _interaction_scope_index(agent: Agent) -> Dict[str, Scope]:
    """Build ``interaction_uuid -> (config, task)`` for one agent.

    Task is attributed to the most recent ``TaskDefinition`` at or before each
    interaction (a stack can hold several when sub-agents are reused).
    """
    config_by_position = _config_by_position(agent)
    index: Dict[str, Scope] = {}
    current_task: Optional[str] = None
    for position, interaction in enumerate(agent.stack.interactions):
        if isinstance(interaction, TaskDefinition) and interaction.task:
            current_task = interaction.task.name
        index[str(interaction.uuid)] = (
            config_by_position.get(position),
            current_task,
        )
    return index


def build_interaction_index(
    storage: Storage, session: Session
) -> Dict[str, Scope]:
    """Scan all agents into a global ``interaction_uuid -> (config, task)`` map."""
    index: Dict[str, Scope] = {}
    for agent_uuid in storage.list_agents():
        try:
            agent = storage.load_agent(agent_uuid, session)
        except Exception as error:  # corrupted/partial agents are skipped
            logger.warning("dream: skipping agent %s: %s", agent_uuid, error)
            continue
        index.update(_interaction_scope_index(agent))
    return index


def scan_provenance(
    storage: Storage, session: Session
) -> List[ArtifactProvenance]:
    """Attribute every episodic artifact to its producing config/task.

    ``Learning`` artifacts are excluded so the dream consolidates episodic
    memory, not its own prior output.
    """
    interaction_index = build_interaction_index(storage, session)
    provenances: List[ArtifactProvenance] = []
    for artifact_id in storage.list_artifacts():
        try:
            record = storage.load_artifact_record(artifact_id)
        except Exception as error:
            logger.warning(
                "dream: skipping artifact %s: %s", artifact_id, error
            )
            continue
        artifact_type = record.get("type", "")
        if artifact_type == LEARNING_TYPE:
            continue
        data = record.get("data", {})
        interaction_id = data.get("interaction")
        config, task = interaction_index.get(interaction_id, (None, None))
        provenances.append(
            ArtifactProvenance(
                artifact_id=artifact_id,
                artifact_type=artifact_type,
                config=config,
                task=task,
                interaction_id=interaction_id,
            )
        )
    return provenances


def group_by_config(
    provenances: List[ArtifactProvenance],
) -> Dict[str, List[ArtifactProvenance]]:
    """Group episodic artifacts by producing config (unattributed dropped)."""
    groups: Dict[str, List[ArtifactProvenance]] = defaultdict(list)
    for provenance in provenances:
        if provenance.config is not None:
            groups[provenance.config].append(provenance)
    return dict(groups)
