"""Launch sub-agent builtin tool."""

import logging
from typing import TYPE_CHECKING, Any, Dict, Optional, Union

from gimle.hugin.agent.task import Task, TaskParameter
from gimle.hugin.interaction.agent_call import AgentCall
from gimle.hugin.tools.tool import Tool, ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


@Tool.register(
    name="builtins.launch_agent",
    description="Launch a sub-agent to perform a specialized task. "
    "The sub-agent will run asynchronously and return its results "
    "when complete. Use this to delegate work to expert agents.",
    parameters={
        "config_name": {
            "type": "string",
            "description": "Name of the agent configuration to launch "
            "(use list_agent_configs to see available options)",
            "required": True,
        },
        "task_name": {
            "type": "string",
            "description": "Name of the task to give the agent",
            "required": True,
        },
        "task_description": {
            "type": "string",
            "description": "Description of what the agent should do",
            "required": True,
        },
        "task_parameters": {
            "type": "object",
            "description": "Parameters to pass to the task "
            "(as a dictionary)",
            "required": False,
        },
    },
    is_interactive=False,
)
def launch_agent(
    config_name: str,
    task_name: str,
    task_description: str,
    stack: "Stack",
    task_parameters: Optional[dict[str, Any]] = None,
) -> Union[ToolResponse, AgentCall]:
    """
    Launch a sub-agent to perform a specialized task.

    Returns an AgentCall that the framework will use to create and
    run the child agent. The parent agent will wait until the child
    completes.

    Args:
        config_name: Name of agent config to use
        task_name: Name for the task
        task_description: What the agent should do
        stack: The stack
        task_parameters: Additional parameters for the task

    Returns:
        AgentCall to spawn the sub-agent, or ToolResponse on error
    """
    try:
        environment = stack.agent.environment

        # Get the agent config
        try:
            config = environment.config_registry.get(config_name)
        except (KeyError, ValueError):
            available = list(environment.config_registry._items.keys())
            return ToolResponse(
                is_error=True,
                content={
                    "error": f"Config '{config_name}' not found",
                    "available_configs": available,
                },
            )

        # Convert raw parameter values to schema format
        schema_parameters: Dict[str, TaskParameter] = {}
        for key, value in (task_parameters or {}).items():
            if isinstance(value, dict) and "type" in value:
                schema_parameters[key] = TaskParameter(
                    type=value["type"],
                    description=value["description"],
                    required=value.get("required", False),
                    value=value.get("value", None),
                )
            else:
                param_type = "string"
                if isinstance(value, bool):
                    param_type = "boolean"
                elif isinstance(value, int):
                    param_type = "integer"
                elif isinstance(value, float):
                    param_type = "number"
                elif isinstance(value, list):
                    param_type = "array"
                elif isinstance(value, dict):
                    param_type = "object"

                schema_parameters[key] = TaskParameter(
                    type=param_type,
                    description=f"Parameter {key}",
                    required=False,
                    value=value,
                )

        # Create task
        task = Task(
            name=task_name,
            description=task_description,
            parameters=schema_parameters,
            prompt=task_description,
            tools=config.tools,
            system_template=config.system_template,
            llm_model=config.llm_model,
        )

        logging.info(
            f"Launching sub-agent with config '{config_name}' "
            f"for task '{task_name}'"
        )

        return AgentCall(
            stack=stack,
            config=config,
            task=task,
        )

    except Exception as e:
        logging.error(f"Error launching agent: {e}")
        import traceback

        traceback.print_exc()
        return ToolResponse(
            is_error=True,
            content={"error": f"Failed to launch agent: {str(e)}"},
        )
