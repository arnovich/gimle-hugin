"""Messaging tools for agent-to-agent communication."""

from typing import TYPE_CHECKING

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


def send_to_agent(agent_id: str, message: str, stack: "Stack") -> ToolResponse:
    """
    Send a message to another agent.

    This wraps agent.message_agent() which inserts an ExternalInput
    into the target agent's stack.
    """
    session = stack.agent.session

    # Find the target agent
    target_agent = None
    for agent in session.agents:
        if agent.id == agent_id:
            target_agent = agent
            break

    if target_agent is None:
        return ToolResponse(
            is_error=True,
            content={
                "error": f"Agent '{agent_id}' not found in session",
                "available_agents": [a.id for a in session.agents],
            },
        )

    # Send the message
    target_agent.message_agent(message)

    return ToolResponse(
        is_error=False,
        content={
            "sent": True,
            "to": agent_id,
            "message": message,
        },
    )
