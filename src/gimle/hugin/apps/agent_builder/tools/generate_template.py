"""Generate template YAML."""

from typing import TYPE_CHECKING

import yaml

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


def generate_template(
    template_name: str,
    template_content: str,
    stack: "Stack",
) -> ToolResponse:
    """Generate a system template YAML.

    Args:
        template_name: Name of the template (snake_case)
        template_content: The system prompt content
        stack: Agent stack (auto-injected)

    Returns:
        ToolResponse with generated template content
    """
    template_data = {
        "name": template_name,
        "template": template_content,
    }

    template_yaml = yaml.dump(
        template_data,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )

    # Store in environment for later writing
    generated_files = stack.agent.environment.env_vars.setdefault(
        "generated_files", {}
    )
    generated_files[f"templates/{template_name}.yaml"] = template_yaml

    return ToolResponse(
        is_error=False,
        content={
            "file_path": f"templates/{template_name}.yaml",
            "content": template_yaml,
            "message": f"Generated template: {template_name}",
        },
    )
