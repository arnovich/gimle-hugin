"""List running agents builtin tool."""

import logging
from typing import TYPE_CHECKING

from gimle.hugin.tools.tool import Tool, ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


@Tool.register(
    name="builtins.list_running_agents",
    description="List all agents currently running in this session, including the current agent and any sub-agents. Returns agent IDs, configs, tasks, and status.",
    parameters={},
    is_interactive=False,
)
def list_running_agents(
    stack: "Stack",
) -> ToolResponse:
    """
    List all agents in the current session.

    Returns information about all agents including current agent
    and any sub-agents that have been launched.

    Args:
        stack: The stack

    Returns:
        ToolResponse with list of running agents
    """
    try:
        session = stack.agent.session

        agents = []
        for agent in session.agents:
            # Get task info
            task_info = None
            if agent.stack.interactions:
                first_interaction = agent.stack.interactions[0]
                if hasattr(first_interaction, "task"):
                    task = first_interaction.task
                    task_info = {
                        "name": (
                            task.name if hasattr(task, "name") else "unknown"
                        ),
                        "description": (
                            task.description
                            if hasattr(task, "description")
                            else None
                        ),
                    }

            # Count interactions and artifacts
            interaction_count = len(agent.stack.interactions)
            artifact_count = sum(
                len(getattr(interaction, "artifacts", []))
                for interaction in agent.stack.interactions
            )

            agent_info = {
                "agent_id": agent.id,
                "config_name": agent.config.name if agent.config else "unknown",
                "is_current_agent": agent.id == stack.agent.id,
                "task": task_info,
                "interactions": interaction_count,
                "artifacts_created": artifact_count,
                "stack_depth": len(agent.stack.interactions),
            }
            agents.append(agent_info)

        result = {
            "session_id": session.id,
            "total_agents": len(agents),
            "current_agent_id": stack.agent.id,
            "agents": agents,
        }

        return ToolResponse(is_error=False, content=result)

    except Exception as e:
        logging.error(f"Error listing running agents: {e}")
        return ToolResponse(
            is_error=True,
            content={"error": f"Failed to list running agents: {str(e)}"},
        )
