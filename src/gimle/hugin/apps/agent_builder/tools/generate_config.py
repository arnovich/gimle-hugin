"""Generate agent config YAML."""

from typing import TYPE_CHECKING, List

import yaml

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


def generate_config(
    agent_name: str,
    description: str,
    system_template: str,
    llm_model: str,
    tools: List[str],
    stack: "Stack",
) -> ToolResponse:
    """Generate an agent configuration YAML.

    Args:
        agent_name: Name of the agent (snake_case)
        description: Human-readable description
        system_template: Name of the system template
        llm_model: LLM model to use
        tools: List of tool names
        stack: Agent stack (auto-injected)

    Returns:
        ToolResponse with generated config content
    """
    # Enforce artifact-saving + completion tools on all generated agents.
    # These are safe defaults even if an agent doesn't end up using them.
    required_tools = [
        "builtins.save_text:save_text",
        "builtins.save_file:save_file",
        "builtins.finish:finish",
    ]
    for t in required_tools:
        if t not in tools:
            tools.append(t)

    config_data = {
        "name": agent_name,
        "description": description,
        "system_template": system_template,
        "llm_model": llm_model,
        "tools": tools,
        "interactive": False,
        "options": {},
    }

    config_yaml = yaml.dump(
        config_data, default_flow_style=False, sort_keys=False
    )

    # Store in environment for later writing
    generated_files = stack.agent.environment.env_vars.setdefault(
        "generated_files", {}
    )
    generated_files[f"configs/{agent_name}.yaml"] = config_yaml

    return ToolResponse(
        is_error=False,
        content={
            "file_path": f"configs/{agent_name}.yaml",
            "content": config_yaml,
            "message": f"Generated config for {agent_name}",
        },
    )
