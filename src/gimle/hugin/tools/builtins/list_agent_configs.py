"""List available agent configs builtin tool."""

import logging
from typing import TYPE_CHECKING

from gimle.hugin.tools.tool import Tool, ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


@Tool.register(
    name="builtins.list_agent_configs",
    description="List all available agent configurations that can be launched. Returns agent names, descriptions, and available tools.",
    parameters={},
    is_interactive=False,
)
def list_agent_configs(stack: "Stack") -> ToolResponse:
    """
    List all available agent configurations.

    Returns information about all agent configs registered in the environment,
    including their names, descriptions, models, and available tools.

    Args:
        stack: The stack

    Returns:
        ToolResponse with list of agent configs
    """
    try:
        environment = stack.agent.environment
        config_registry = environment.config_registry

        configs = []
        for config_name, config in config_registry._items.items():
            config_info = {
                "name": config.name,
                "description": config.description or "No description",
                "llm_model": config.llm_model,
                "system_template": config.system_template,
                "tools": config.tools if config.tools else [],
                "tool_count": len(config.tools) if config.tools else 0,
            }
            configs.append(config_info)

        result = {
            "total_configs": len(configs),
            "configs": configs,
        }

        return ToolResponse(is_error=False, content=result)

    except Exception as e:
        logging.error(f"Error listing agent configs: {e}")
        return ToolResponse(
            is_error=True,
            content={"error": f"Failed to list agent configs: {str(e)}"},
        )
