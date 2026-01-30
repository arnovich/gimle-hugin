"""List available agents builtin tool."""

import logging
from typing import TYPE_CHECKING

from gimle.hugin.tools.tool import Tool, ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


@Tool.register(
    name="builtins.list_agents",
    description="List all available agents that can be launched, including builtin agents like agent_builder. Returns agent names, descriptions, and available tools.",
    parameters={},
    is_interactive=False,
)
def list_agents(stack: "Stack") -> ToolResponse:
    """
    List all available agent configurations.

    Returns information about all agent configs registered in the environment.
    Builtin agents (like agent_builder) are included only if the calling
    agent's config has enable_builtin_agents=True (the default).

    Args:
        stack: The stack

    Returns:
        ToolResponse with list of agents
    """
    try:
        environment = stack.agent.environment
        agent_config = stack.agent.config

        # Check if builtin agents should be included
        include_builtins = getattr(agent_config, "enable_builtin_agents", True)

        # Get configs based on whether builtins are enabled
        if include_builtins:
            all_configs = environment.get_all_configs()
        else:
            all_configs = dict(environment.config_registry._items)

        agents = []
        for config_name, config in all_configs.items():
            # Use the key as the name for builtins (e.g., "builtins.agent_builder")
            display_name = (
                config_name
                if config_name.startswith("builtins.")
                else config.name
            )
            agent_info = {
                "name": display_name,
                "description": config.description or "No description",
                "llm_model": config.llm_model,
                "system_template": config.system_template,
                "tools": config.tools if config.tools else [],
                "tool_count": len(config.tools) if config.tools else 0,
                "is_builtin": config_name.startswith("builtins."),
            }
            agents.append(agent_info)

        # Sort: builtins first, then alphabetically
        agents.sort(key=lambda a: (not a["is_builtin"], a["name"]))

        result = {
            "total_agents": len(agents),
            "agents": agents,
        }

        return ToolResponse(is_error=False, content=result)

    except Exception as e:
        logging.error(f"Error listing agents: {e}")
        return ToolResponse(
            is_error=True,
            content={"error": f"Failed to list agents: {str(e)}"},
        )
